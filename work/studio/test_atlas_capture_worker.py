import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from atlas_capture_worker import CaptureWorker


class WorkerTests(unittest.TestCase):
    def test_settling_probes_are_saved_but_never_used_for_alignment(self):
        from analyze_live_atlas import frame_sequence
        with tempfile.TemporaryDirectory() as tmp,patch('atlas_capture_worker.CaptureAlignment') as align:
            worker=CaptureWorker(Path(tmp),{})
            frame=np.zeros((20,20,3),np.uint8)
            early=np.full((10,10,3),40,np.uint8)
            record=dict(kind='frame',name='grid_001')
            worker.submit('grid_001',frame,(2,2,12,12),record,dict(dx=10,dy=0),lambda:None,
                          probes=(('early',early),('check',early.copy())))
            worker.close()
            self.assertEqual(align.return_value.append.call_count,1)
            np.testing.assert_array_equal(align.return_value.append.call_args.args[1],frame[2:12,2:12])
            self.assertEqual(len(record['settling_probe_files']),2)
            for name in record['settling_probe_files']:
                np.testing.assert_array_equal(np.array(Image.open(Path(tmp)/name)),early)
            sequence=frame_sequence([dict(kind='frame',name='max_sampling'),record,
                                     dict(kind='command',holdout=True)])
            self.assertEqual(sequence['names'],['max_sampling','grid_001'])
            self.assertEqual(sequence['holdout_indices'],[1])

    def test_background_save_preserves_rgb_and_order(self):
        with tempfile.TemporaryDirectory() as tmp,patch('atlas_capture_worker.CaptureAlignment') as align:
            worker=CaptureWorker(Path(tmp),{})
            records=[];images=[]
            for index in range(4):
                frame=np.random.default_rng(index).integers(0,256,(40,50,3),dtype=np.uint8)
                record=dict(png_seconds=None,storage_error=None)
                worker.submit(str(index),frame,(2,3,32,33),record,{'dx':index},lambda:None)
                records.append(record);images.append(frame)
            worker.close()
            self.assertTrue(worker.closed)
            for i,frame in enumerate(images):
                np.testing.assert_array_equal(np.array(Image.open(Path(tmp)/f'{i}.png')),frame)
                np.testing.assert_array_equal(np.array(Image.open(Path(tmp)/f'{i}_board.png')),frame[3:33,2:32])
                self.assertIsNotNone(records[i]['png_seconds'])
            self.assertEqual([c.args[0] for c in align.return_value.append.call_args_list],['0','1','2','3'])

    def test_registration_failure_keeps_every_saved_frame_for_serial_retry(self):
        with tempfile.TemporaryDirectory() as tmp,patch('atlas_capture_worker.CaptureAlignment') as align:
            align.return_value.append.side_effect=ValueError('unreliable texture')
            worker=CaptureWorker(Path(tmp),{})
            for i in range(3):
                worker.submit(str(i),np.zeros((10,10,3),np.uint8),(1,1,9,9),{},None,lambda:None)
            self.assertIsNone(worker.close())
            self.assertEqual(worker.error,'unreliable texture')
            self.assertEqual(len(list(Path(tmp).glob('*_board.png'))),3)

    def test_backpressure_remains_cancellable_and_closes_worker(self):
        entered=threading.Event();release=threading.Event()
        def blocked(*args):entered.set();release.wait(3)
        with tempfile.TemporaryDirectory() as tmp,patch('atlas_capture_worker.CaptureAlignment'):
            worker=CaptureWorker(Path(tmp),{})
            try:
                with patch.object(worker,'_process',side_effect=blocked):
                    for i in range(2):worker.submit(str(i),None,None,{},None,lambda:None)
                    self.assertTrue(entered.wait(1))
                    def stop():raise InterruptedError('F9')
                    with self.assertRaises(InterruptedError):worker.submit('2',None,None,{},None,stop)
            finally:release.set();worker.close()


if __name__=='__main__':unittest.main()
