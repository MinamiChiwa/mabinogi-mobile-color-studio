import json
from pathlib import Path
import tempfile
import threading
import unittest

import numpy as np
from PIL import Image

from execution_diagnostics import ExecutionDiagnostics


class ExecutionDiagnosticsTests(unittest.TestCase):
    def test_slow_storage_returns_before_disk_and_retains_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            writer=ExecutionDiagnostics(max_jobs=1)
            entered=threading.Event();release=threading.Event()
            write=writer._write
            def slow(*args):
                entered.set();release.wait(5);write(*args)
            writer._write=slow
            image=np.full((10,10,3),17,np.uint8);data={'result':{'value':1}}
            done=writer.submit(folder,'first',data,{'first.png':image})
            try:
                self.assertTrue(entered.wait(2))
                self.assertFalse(done.is_set())
                image[:]=99;data['result']['value']=2
                self.assertIsNone(writer.submit(folder,'second',{},{}))
            finally:release.set()
            self.assertTrue(done.wait(5))
            self.assertEqual(json.loads((Path(folder)/'first.json').read_text())['result']['value'],1)
            with Image.open(Path(folder)/'first.png') as saved:
                np.testing.assert_array_equal(np.asarray(saved),np.full((10,10,3),17,np.uint8))

    def test_large_images_are_omitted_without_losing_route_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            writer=ExecutionDiagnostics(max_bytes=10)
            done=writer.submit(folder,'first',{'motion_frames':{'before':'before.png'},'route':[1,2]},
                               {'before.png':np.zeros((10,10,3),np.uint8)})
            self.assertTrue(done.wait(5))
            data=json.loads((Path(folder)/'first.json').read_text())
            self.assertTrue(data['diagnostic_storage']['images_omitted'])
            self.assertEqual(data['motion_frames'],{})
            self.assertEqual(data['route'],[1,2])
            self.assertFalse((Path(folder)/'before.png').exists())

    def test_storage_failure_does_not_poison_later_jobs(self):
        writer=ExecutionDiagnostics(max_jobs=1)
        def fail(*args):raise OSError('disk unavailable')
        writer._write=fail
        self.assertTrue(writer.submit('unused','first',{},{}).wait(5))
        self.assertTrue(writer.submit('unused','second',{},{}).wait(5))


if __name__=='__main__':unittest.main()
