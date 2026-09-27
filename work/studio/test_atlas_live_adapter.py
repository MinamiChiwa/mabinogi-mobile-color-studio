import tempfile
import unittest
import threading
import json
import numpy as np
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from atlas_live_adapter import acquire_current,_execute_recorded


class LiveAdapterTests(unittest.TestCase):
    def test_failure_saves_both_existing_motion_frames_and_diagnostics(self):
        with tempfile.TemporaryDirectory() as folder:
            adapter=SimpleNamespace(last_motion_before=None,last_motion_after=None,
                                    last_motion_diagnostics=None)
            before=np.full((12,12,3),20,np.uint8);after=before+10
            diagnostics={'passed':False,'reason':'insufficient_inliers'}
            def fail(*args,**kwargs):
                adapter.last_motion_before=before;adapter.last_motion_after=after
                adapter.last_motion_diagnostics=diagnostics;adapter.last_frame=after
                kwargs['emit']('atlas_command',{'step':1,'action':'drag','command':[-49,80]})
                raise RuntimeError('配准失败')
            report=dict(adapter=adapter,capture_folder=Path(folder))
            owner=SimpleNamespace(event=lambda *a,**k:None)
            with patch('atlas_live_adapter.execute_candidate',side_effect=fail):
                with self.assertRaises(RuntimeError):
                    _execute_recorded(owner,report,{'id':1},[],SimpleNamespace(id='batch'),before)
            data=json.loads((Path(folder)/'execution/attempt-01.json').read_text(encoding='utf-8'))
            self.assertEqual(data['last_registration'],diagnostics)
            self.assertEqual(data['events'][0]['command'],[-49,80])
            for label,expected in (('before',before),('after',after)):
                saved=Image.open(Path(folder)/'execution'/data['motion_frames'][label])
                np.testing.assert_array_equal(np.array(saved),expected)
            # A later F9 before capture must not attribute the previous pair
            # to a new attempt, and saving never requests another screenshot.
            with patch('atlas_live_adapter.execute_candidate',side_effect=InterruptedError('F9')):
                with self.assertRaises(InterruptedError):
                    _execute_recorded(owner,report,{'id':1},[],SimpleNamespace(id='batch'),before)
            second=json.loads((Path(folder)/'execution/attempt-02.json').read_text(encoding='utf-8'))
            self.assertIsNone(second['last_registration']);self.assertEqual(second['motion_frames'],{})

    def test_failed_execution_saves_last_frame_without_recapturing(self):
        with tempfile.TemporaryDirectory() as folder:
            adapter=SimpleNamespace(last_frame=np.zeros((12,12,3),np.uint8))
            report=dict(adapter=adapter,capture_folder=Path(folder))
            owner=SimpleNamespace(event=lambda *a,**k:None)
            with patch('atlas_live_adapter.execute_candidate',side_effect=InterruptedError('F9')):
                with self.assertRaises(InterruptedError):
                    _execute_recorded(owner,report,{'id':1},[],SimpleNamespace(id='batch'),None)
            data=json.loads((Path(folder)/'execution/attempt-01.json').read_text())
            self.assertEqual(data['error'],'F9');self.assertIsNone(data['result'])
            self.assertTrue((Path(folder)/'execution/attempt-01.png').is_file())

    def test_acquire_waits_for_manual_entry(self):
        with tempfile.TemporaryDirectory() as folder:
            target=object()
            owner=SimpleNamespace(stop=threading.Event())
            with patch('atlas_live_adapter.acquire') as acquire:
                acquire.return_value={'folder':folder}
                result=acquire_current(owner,[],folder,
                                       strategy='grid',entry_size=(1280,960),target=target,activate=True)
                self.assertEqual(result['folder'],folder)
                self.assertEqual(acquire.call_args.args,(Path(folder),None))
                self.assertEqual(acquire.call_args.kwargs['strategy'],'grid')
                self.assertEqual(acquire.call_args.kwargs['row_stagger'],.05)
                self.assertIs(acquire.call_args.kwargs['target'],target)
                self.assertTrue(acquire.call_args.kwargs['activate'])
                self.assertEqual(acquire.call_args.kwargs['entry_size'],(1280,960))
                self.assertIs(acquire.call_args.kwargs['stop'],owner.stop)


if __name__=='__main__':unittest.main()
