import unittest
from subprocess import CompletedProcess, TimeoutExpired
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image

import vision


class Clock:
    def __init__(self, value=10.):
        self.value=value

    def __call__(self):
        return self.value


class VisionStageDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.clock=Clock()
        self.image=np.full((100,100,3),255,np.uint8)
        self.cards=[(0,0,80,80)]
        self.markers=[(40,90)]
        self.addCleanup(setattr,vision,'OCR_AVAILABLE',vision.OCR_AVAILABLE)
        vision.OCR_AVAILABLE=True

    def read(self,deadline,**kwargs):
        return vision.read_codes(self.image,self.cards,self.markers,
                                 deadline=deadline,clock=self.clock,**kwargs)

    def test_variant_processes_share_the_absolute_remaining_time(self):
        observed=[]
        check=Mock()
        def run(*args,**kwargs):
            observed.append(kwargs['timeout'])
            self.clock.value+=min(.75,kwargs['timeout'])
            return CompletedProcess([],0,b'',b'')
        with patch('vision.subprocess.run',side_effect=run):
            with self.assertRaisesRegex(TimeoutError,'OCR observation deadline expired'):
                self.read(12.,check=check)
        self.assertEqual(observed,[2.,1.25,.5])
        self.assertEqual(self.clock.value,12.)
        self.assertGreater(check.call_count,len(observed)*2)
        self.assertTrue(vision.OCR_AVAILABLE)

    def test_expired_budget_does_not_launch_any_process(self):
        with patch('vision.subprocess.run') as process:
            with self.assertRaises(TimeoutError):self.read(10.)
        process.assert_not_called()
        self.assertTrue(vision.OCR_AVAILABLE)

    def test_success_arriving_at_deadline_is_not_accepted(self):
        def run(*args,**kwargs):
            self.clock.value=11.
            return CompletedProcess([],0,b'#FFFFFF',b'')
        with patch('vision.subprocess.run',side_effect=run) as process:
            with self.assertRaises(TimeoutError):self.read(11.)
        self.assertEqual(process.call_count,1)
        self.assertTrue(vision.OCR_AVAILABLE)

    def test_subprocess_expiry_stops_before_another_variant(self):
        def run(*args,**kwargs):
            self.clock.value+=kwargs['timeout']
            raise TimeoutExpired('tesseract',kwargs['timeout'])
        with patch('vision.subprocess.run',side_effect=run) as process:
            with self.assertRaises(TimeoutError):self.read(10.4)
        self.assertEqual(process.call_count,1)
        self.assertAlmostEqual(process.call_args.kwargs['timeout'],.4)
        self.assertTrue(vision.OCR_AVAILABLE)

    def test_crop_fallback_uses_the_same_deadline(self):
        observed=[]
        def run(*args,**kwargs):
            observed.append(kwargs['timeout'])
            self.clock.value+=.125
            return CompletedProcess([],0,b'#FFFFFF' if len(observed)==8 else b'',b'')
        with patch('vision.subprocess.run',side_effect=run):
            self.assertEqual(self.read(11.125),['#FFFFFF'])
        self.assertEqual(len(observed),8)
        self.assertEqual(observed[-1],.25)
        self.assertEqual(self.clock.value,11.)

    def test_image_encoding_is_charged_before_process_timeout(self):
        save=Image.Image.save
        def slow_save(image,*args,**kwargs):
            save(image,*args,**kwargs)
            self.clock.value+=.25
        with patch.object(Image.Image,'save',slow_save), \
             patch('vision.subprocess.run',return_value=CompletedProcess([],0,b'#FFFFFF',b'')) as process:
            self.assertEqual(self.read(11.),['#FFFFFF'])
        self.assertEqual(process.call_args.kwargs['timeout'],.75)

    def test_guard_interrupt_before_ocr_is_propagated(self):
        class UserStop(Exception):pass
        with patch('vision.subprocess.run') as process:
            with self.assertRaises(UserStop):self.read(12.,check=Mock(side_effect=UserStop()))
        process.assert_not_called()

    def test_legacy_calls_do_not_require_new_mock_keywords(self):
        def text(image,config,timeout=2):return '#FFFFFF'
        with patch('vision._tesseract',side_effect=text) as process:
            self.assertEqual(vision.read_codes(self.image,self.cards,self.markers),['#FFFFFF'])
        self.assertEqual(process.call_count,1)


if __name__=='__main__':unittest.main()
