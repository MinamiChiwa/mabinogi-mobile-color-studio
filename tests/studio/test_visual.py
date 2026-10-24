"""Regression against real captures; never sends game input."""
import unittest
from pathlib import Path
from PIL import Image
import numpy as np
from vision import configure_ocr,recognize,result_colors,measure_board_motion

@unittest.skipUnless(Path('work/studio/data/sessions/20260917-124756/start.png').exists(), 'Private game captures are not distributed')
class CapturedSceneTests(unittest.TestCase):
    @unittest.skipUnless(Path('outputs/release/ColorStudio/data/sessions/20260917-161321/start.png').exists() or Path('work/studio/release-test-data/sessions/20260917-161321/start.png').exists(), 'Private game capture is not distributed')
    def test_small_portrait_cards_separate_from_white_stems(self):
        path=Path('work/studio/release-test-data/sessions/20260917-161321/start.png')
        if not path.exists():path=Path('outputs/release/ColorStudio/data/sessions/20260917-161321/start.png')
        scene=recognize(np.array(Image.open(path)))
        self.assertEqual(scene.colors,['#5D8264','#534B42','#C28860'])
        self.assertEqual(scene.seconds,99)
        self.assertEqual(scene.markers,[(224,533),(347,522),(471,541)])
    @unittest.skipUnless(Path('work/studio/release-test-data/sessions/20260917-155156/step-01.png').exists(), 'Private game capture is not distributed')
    def test_maximized_timer_retains_all_three_digits(self):
        folder=Path('work/studio/release-test-data/sessions/20260917-155156')
        for name,seconds in [('start.png',112),('step-01.png',108)]:
            with self.subTest(name=name):
                self.assertEqual(recognize(np.array(Image.open(folder/name))).seconds,seconds)
    def test_repeated_narrow_hex_glyphs(self):
        im=np.array(Image.open('work/studio/data/sessions/20260917-124756/start.png'))
        self.assertEqual(recognize(im).colors,['#597961','#7F7F7F','#A95C40'])
    def test_three_negative_wheel_ticks_shrink_texture(self):
        folder=Path('work/studio/data/sessions/20260917-121940')
        a=np.array(Image.open(folder/'right.png'));b=np.array(Image.open(folder/'wheel.png'))
        motion=measure_board_motion(a,b,(203,379,665,841))
        self.assertIsNotNone(motion)
        self.assertAlmostEqual(motion['scale'],.9706,delta=.005)
        self.assertLess(abs(motion['angle']),.5)
    def test_rotation_anchored_at_right_button_down(self):
        folder=Path('work/studio/data/sessions/20260917-120841')
        a=np.array(Image.open(folder/'left.png'));b=np.array(Image.open(folder/'right.png'))
        motion=measure_board_motion(a,b,(203,379,665,841))
        self.assertIsNotNone(motion)
        self.assertAlmostEqual(motion['angle'],22.7,delta=1)
        self.assertAlmostEqual(motion['scale'],1,delta=.02)
        scene=recognize(a,False)
        rotated=recognize(b,False,previous=scene)
        self.assertEqual(rotated.markers,scene.markers)
    def test_real_right_drag_is_rotation_not_translation(self):
        folder=Path('work/studio/data/sessions/20260917-095051')
        a=np.array(Image.open(folder/'left.png'));b=np.array(Image.open(folder/'right.png'))
        motion=measure_board_motion(a,b,(40,410,475,835))
        self.assertIsNotNone(motion)
        self.assertAlmostEqual(motion['angle'],17.8,delta=1)
        self.assertAlmostEqual(motion['scale'],1,delta=.02)
        self.assertGreater(motion['inliers'],100)
    @classmethod
    def setUpClass(cls):configure_ocr()
    def test_landscape_and_rescaled_captures(self):
        image=Image.open('work/evidence/trial3-initial.png').convert('RGB')
        for scale in [.8,1,1.25]:
            with self.subTest(scale=scale):
                resized=image.resize((round(image.width*scale),round(image.height*scale)))
                scene=recognize(np.array(resized))
                self.assertEqual(scene.colors,['#F5B4BF','#C87979','#379C8D'])
                self.assertEqual(scene.seconds,116)
    def test_portrait_captures(self):
        expected={'start.png':['#C2CB6D','#7D6B64','#B38559'],'left.png':['#A59B66','#8CB584','#E280A5'],'right.png':['#ECBFAC','#AAADAE','#08A097'],'wheel.png':['#EBBB95','#928487','#08A097']}
        for name,colors in expected.items():
            with self.subTest(name=name):
                scene=recognize(np.array(Image.open(Path('work/studio/data/sessions/20260917-095051')/name)))
                self.assertEqual(scene.colors,colors)
                self.assertTrue(90<scene.seconds<110)
    def test_result_page(self):
        im=np.array(Image.open('work/studio/data/sessions/20260917-100710/start.png'))
        self.assertEqual(result_colors(im),['#26222B','#099DA4','#DBC9C0'])
    def test_wider_portrait_capture(self):
        im=np.array(Image.open('work/studio/data/sessions/20260917-110637/start.png'))
        scene=recognize(im)
        self.assertEqual(scene.colors,['#E5569C','#87A62F',None])  # Reject ambiguous 6/E instead of reporting a wrong exact code.
        self.assertEqual(scene.seconds,110)

    def test_stable_markers_survive_board_changes(self):
        folder=Path('work/studio/data/sessions/20260917-111455')
        initial=recognize(np.array(Image.open(folder/'start.png')))
        moved=recognize(np.array(Image.open(folder/'step-02.png')),previous=initial)
        self.assertEqual(moved.markers,initial.markers)
        self.assertEqual(moved.colors[0],'#001346')

    def test_white_marker(self):
        fixture=Path('work/studio/release-test-data/sessions/20260917-102739/start.png')
        if not fixture.exists():self.skipTest('Local private capture fixture is not distributed')
        im=np.array(Image.open(fixture))
        scene=recognize(im,False)
        self.assertLess(abs(scene.markers[1][1]-623),5)

if __name__=='__main__':unittest.main()
