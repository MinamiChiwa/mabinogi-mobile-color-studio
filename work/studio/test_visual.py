"""Regression against real captures; never sends game input."""
import unittest
import os
from pathlib import Path
from PIL import Image
import numpy as np
from vision import configure_ocr,recognize,result_colors,measure_board_motion

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = Path(os.environ.get('COLORSTUDIO_TEST_FIXTURES', ROOT / 'tests/fixtures'))


def fixture_path(relative):
    """Prefer persistent test assets; accept legacy local captures during migration."""
    relative = Path(relative)
    candidates = (FIXTURE_ROOT / relative, ROOT / 'work/studio/data' / relative,
                  ROOT / 'work/studio/release-test-data' / relative,
                  ROOT / 'outputs/release/ColorStudio/data' / relative)
    if relative.parts[0] == 'evidence':
        candidates += (ROOT / 'work' / relative,)
    return next((path for path in candidates if path.is_file()), candidates[0])


REQUIRED_FIXTURES = {
    'test_small_portrait_cards_separate_from_white_stems': ('sessions/20260917-161321/start.png',),
    'test_maximized_timer_retains_all_three_digits': tuple(
        'sessions/20260917-155156/' + name for name in ('start.png', 'step-01.png')),
    'test_repeated_narrow_hex_glyphs': ('sessions/20260917-124756/start.png',),
    'test_three_negative_wheel_ticks_shrink_texture': tuple(
        'sessions/20260917-121940/' + name for name in ('right.png', 'wheel.png')),
    'test_rotation_anchored_at_right_button_down': tuple(
        'sessions/20260917-120841/' + name for name in ('left.png', 'right.png')),
    'test_real_right_drag_is_rotation_not_translation': tuple(
        'sessions/20260917-095051/' + name for name in ('left.png', 'right.png')),
    'test_landscape_and_rescaled_captures': ('evidence/trial3-initial.png',),
    'test_portrait_captures': tuple('sessions/20260917-095051/' + name
        for name in ('start.png', 'left.png', 'right.png', 'wheel.png')),
    'test_result_page': ('sessions/20260917-100710/start.png',),
    'test_wider_portrait_capture': ('sessions/20260917-110637/start.png',),
    'test_stable_markers_survive_board_changes': tuple('sessions/20260917-111455/' + name
        for name in ('start.png', 'step-02.png')),
    'test_white_marker': ('sessions/20260917-102739/start.png',),
}
NO_OCR_CASES = frozenset({
    'test_three_negative_wheel_ticks_shrink_texture',
    'test_rotation_anchored_at_right_button_down',
    'test_real_right_drag_is_rotation_not_translation', 'test_white_marker',
})


class CapturedSceneTests(unittest.TestCase):
    def setUp(self):
        missing = [name for name in REQUIRED_FIXTURES[self._testMethodName]
                   if not fixture_path(name).is_file()]
        if missing:
            self.skipTest('Missing private fixture(s): ' + ', '.join(missing))
        if self._testMethodName not in NO_OCR_CASES and not configure_ocr():
            self.skipTest('Tesseract unavailable for this OCR fixture test')

    def test_small_portrait_cards_separate_from_white_stems(self):
        path=fixture_path('sessions/20260917-161321/start.png')
        scene=recognize(np.array(Image.open(path)))
        self.assertEqual(scene.colors,['#5D8264','#534B42','#C28860'])
        self.assertEqual(scene.seconds,99)
        self.assertEqual(scene.markers,[(224,533),(347,522),(471,541)])
    def test_maximized_timer_retains_all_three_digits(self):
        for name,seconds in [('start.png',112),('step-01.png',108)]:
            with self.subTest(name=name):
                self.assertEqual(recognize(np.array(Image.open(fixture_path('sessions/20260917-155156/'+name)))).seconds,seconds)
    def test_repeated_narrow_hex_glyphs(self):
        im=np.array(Image.open(fixture_path('sessions/20260917-124756/start.png')))
        self.assertEqual(recognize(im).colors,['#597961','#7F7F7F','#A95C40'])
    def test_three_negative_wheel_ticks_shrink_texture(self):
        a=np.array(Image.open(fixture_path('sessions/20260917-121940/right.png')))
        b=np.array(Image.open(fixture_path('sessions/20260917-121940/wheel.png')))
        motion=measure_board_motion(a,b,(203,379,665,841))
        self.assertIsNotNone(motion)
        self.assertAlmostEqual(motion['scale'],.9706,delta=.005)
        self.assertLess(abs(motion['angle']),.5)
    def test_rotation_anchored_at_right_button_down(self):
        a=np.array(Image.open(fixture_path('sessions/20260917-120841/left.png')))
        b=np.array(Image.open(fixture_path('sessions/20260917-120841/right.png')))
        motion=measure_board_motion(a,b,(203,379,665,841))
        self.assertIsNotNone(motion)
        self.assertAlmostEqual(motion['angle'],22.7,delta=1)
        self.assertAlmostEqual(motion['scale'],1,delta=.02)
        scene=recognize(a,False)
        rotated=recognize(b,False,previous=scene)
        self.assertEqual(rotated.markers,scene.markers)
    def test_real_right_drag_is_rotation_not_translation(self):
        a=np.array(Image.open(fixture_path('sessions/20260917-095051/left.png')))
        b=np.array(Image.open(fixture_path('sessions/20260917-095051/right.png')))
        motion=measure_board_motion(a,b,(40,410,475,835))
        self.assertIsNotNone(motion)
        self.assertAlmostEqual(motion['angle'],17.8,delta=1)
        self.assertAlmostEqual(motion['scale'],1,delta=.02)
        self.assertGreater(motion['inliers'],100)
    def test_landscape_and_rescaled_captures(self):
        image=Image.open(fixture_path('evidence/trial3-initial.png')).convert('RGB')
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
                scene=recognize(np.array(Image.open(fixture_path('sessions/20260917-095051/'+name))))
                self.assertEqual(scene.colors,colors)
                self.assertTrue(90<scene.seconds<110)
    def test_result_page(self):
        im=np.array(Image.open(fixture_path('sessions/20260917-100710/start.png')))
        self.assertEqual(result_colors(im),['#26222B','#099DA4','#DBC9C0'])
    def test_wider_portrait_capture(self):
        im=np.array(Image.open(fixture_path('sessions/20260917-110637/start.png')))
        scene=recognize(im)
        self.assertEqual(scene.colors,['#E5569C','#87A62F',None])  # Reject ambiguous 6/E instead of reporting a wrong exact code.
        self.assertEqual(scene.seconds,110)

    def test_stable_markers_survive_board_changes(self):
        initial=recognize(np.array(Image.open(fixture_path('sessions/20260917-111455/start.png'))))
        moved=recognize(np.array(Image.open(fixture_path('sessions/20260917-111455/step-02.png'))),previous=initial)
        self.assertEqual(moved.markers,initial.markers)
        self.assertEqual(moved.colors[0],'#001346')

    def test_white_marker(self):
        fixture=fixture_path('sessions/20260917-102739/start.png')
        im=np.array(Image.open(fixture))
        scene=recognize(im,False)
        self.assertLess(abs(scene.markers[1][1]-623),5)

if __name__=='__main__':unittest.main()
