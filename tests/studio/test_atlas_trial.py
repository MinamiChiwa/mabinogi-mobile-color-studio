import unittest
from pathlib import Path
import numpy as np
from PIL import Image
import pytesseract
from atlas_trial import calculation_should_stop,load_atlas,load_reference_frame,motion,timer
from atlas_execution import checked_translation
from vision import recognize,read_codes

ROOT=Path(__file__).resolve().parents[2]
CAPTURE=ROOT/'outputs/live-atlas-20260923-01'
OCR=ROOT/'outputs/dependencies/ocr/tesseract.exe'


class TrialBudgetTests(unittest.TestCase):
    def test_reference_frame_falls_back_to_grid_capture(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'grid_001.png'
            Image.new('RGB',(3,2),(1,2,3)).save(path)
            image=load_reference_frame(tmp)
            self.assertEqual(image.shape,(2,3,3))
            self.assertEqual(image[0,0].tolist(),[1,2,3])

    def test_reference_frame_prefers_max_sampling_over_legacy_low_frame(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            Image.new('RGB',(3,2),(1,2,3)).save(Path(tmp)/'low_0.png')
            Image.new('RGB',(3,2),(4,5,6)).save(Path(tmp)/'max_sampling.png')
            image=load_reference_frame(tmp)
            self.assertEqual(image[0,0].tolist(),[4,5,6])

    def test_candidate_calculation_keeps_time_for_default_without_old_30_second_cutoff(self):
        import threading
        stop=threading.Event()
        self.assertFalse(calculation_should_stop(stop,100,75))
        self.assertTrue(calculation_should_stop(stop,100,89))
        stop.set()
        self.assertTrue(calculation_should_stop(stop,100,50))


@unittest.skipUnless((CAPTURE/'heldout_xy.png').exists() and OCR.exists(),'Local native captures and OCR are not distributed')
class TrialCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old=pytesseract.pytesseract.tesseract_cmd
        pytesseract.pytesseract.tesseract_cmd=str(OCR)
    @classmethod
    def tearDownClass(cls):pytesseract.pytesseract.tesseract_cmd=cls.old
    def test_actual_timer_and_hex(self):
        image=np.array(Image.open(CAPTURE/'heldout_xy.png'))
        scene=recognize(image,False)
        self.assertEqual(timer(image),87)
        self.assertEqual(read_codes(image,scene.cards,scene.markers),['#623D37','#6D4E50','#848484'])
    def test_cached_atlas_revalidation_on_unseen_pose(self):
        atlas=load_atlas(CAPTURE/'analysis/expanded/atlas.npz')
        reference=np.array(Image.open(CAPTURE/'low_0.png'))
        current=np.array(Image.open(CAPTURE/'heldout_xy.png'))
        scene=recognize(reference,False)
        offset=checked_translation(motion(reference,current,scene))
        l,t,r,b=scene.board
        for region in range(3):
            values,valid=atlas.sample(region,[np.array(scene.markers[region])-[l,t]],offset)
            self.assertTrue(valid[0])
            expected=np.array([[98,61,55],[109,78,80],[132,132,132]])[region]
            self.assertLess(np.linalg.norm(values[0]-expected),9)


if __name__=='__main__':unittest.main()
