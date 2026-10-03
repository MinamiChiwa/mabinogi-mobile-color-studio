"""Guard equivalent startup work reduction, without driving the game."""
from dataclasses import replace
import threading
import unittest
from unittest.mock import patch

import cv2
import numpy as np

import vision
from atlas_masks import board_texture_mask
from live_atlas_capture import ZoomMotionTracker


class StartupRecognitionTests(unittest.TestCase):
    def test_timer_track_signal_locates_resizable_horizontal_bar(self):
        image=np.zeros((300,500,3),np.uint8)
        image[24:31,75:390]=235
        track=vision.timer_bar_signal(image,unit=30)
        self.assertIsNotNone(track)
        self.assertEqual(track['left'],75)
        self.assertEqual(track['top'],24)
        self.assertGreaterEqual(track['fill_end'],389)
        self.assertGreater(track['confidence'],.7)

    def test_countdown_only_still_checks_geometry_and_timer(self):
        image=np.zeros((300,300,3),np.uint8)
        scene=vision.Scene([(70,40,30,30),(130,40,30,30),(190,40,30,30)],
                           [(85,130),(145,170),(205,150)],(55,78,235,258),
                           ['#FFFFFF']*3,120,None)
        with patch('vision.color_cards',return_value=scene.cards), \
             patch('vision.read_codes',return_value=['#FFFFFF']*3) as codes, \
             patch('vision.timer_seconds',return_value=119) as timer:
            actual=vision.recognize(image,previous=scene,read_colors=False)
            codes.assert_not_called()
            timer.assert_called_once_with(image,unit=30,previous=120)
            self.assertEqual(actual.colors,[None]*3)
            self.assertEqual((actual.board,actual.markers,actual.seconds),
                             (scene.board,scene.markers,119))
            self.assertEqual(vision.recognize(image,previous=scene).colors,['#FFFFFF']*3)
            codes.assert_called_once()
            with patch('vision.color_cards',return_value=None):
                with self.assertRaises(ValueError):
                    vision.recognize(image,previous=scene,read_colors=False)

    def test_timer_recheck_uses_all_variants_with_two_workers(self):
        # Sequential execution cannot pass this barrier. The test also checks
        # the bound on concurrency and that a late better reading still wins.
        barrier=threading.Barrier(2,timeout=5)
        lock=threading.Lock();calls=[];active=0;maximum=0
        def read(crop,whitelist,psm):
            nonlocal active,maximum
            with lock:
                active+=1;maximum=max(active,maximum)
                calls.append((crop.shape,psm,whitelist))
            try:
                barrier.wait()
                return '4119' if crop.shape[1]>=200 and psm==11 else '19'
            finally:
                with lock:active-=1
        with patch('vision.ocr',side_effect=read):
            value=vision.timer_seconds(np.zeros((960,1280,3),np.uint8),unit=81,previous=120)
        self.assertEqual(value,119)
        self.assertEqual(maximum,2)
        self.assertEqual(len(calls),12)
        self.assertEqual(sum(psm==6 for _,psm,_ in calls),6)
        self.assertTrue(all(whitelist=='0123456789' for _,_,whitelist in calls))

    def test_parallel_timer_preserves_missing_and_increasing_readings(self):
        image=np.zeros((960,1280,3),np.uint8)
        for text,previous,expected in (('',20,None),('420',20,20),
                                        ('119',5,119),('21 20',20,20)):
            with self.subTest(text=text,previous=previous),patch('vision.ocr',return_value=text) as read:
                self.assertEqual(vision.timer_seconds(image,unit=81,previous=previous),expected)
                self.assertEqual(read.call_count,12)

    def test_short_previous_reading_can_be_corrected_by_repeated_long_timer(self):
        image=np.zeros((960,1280,3),np.uint8)
        with patch('vision.ocr',return_value='119') as read:
            self.assertEqual(vision.timer_seconds(image,unit=81,previous=20),119)
        self.assertEqual(read.call_count,12)

    def test_timer_accepts_localized_suffixes_and_unicode_digits(self):
        image=np.zeros((960,1280,3),np.uint8)
        for text,expected in (('80秒',80),('남은 시간 95초',95),('１２５ s',125)):
            with self.subTest(text=text),patch('vision.ocr',return_value=text):
                self.assertEqual(vision.timer_seconds(image,unit=81),expected)

    def test_initial_countdown_checks_broad_crop_before_accepting_short_suffix(self):
        # The narrow crops may see only the trailing ``19`` of a 119-second
        # timer.  Initial recognition must continue through the broad crop.
        def read(crop,whitelist,psm):
            return '119' if crop.shape[1] >= 400 else '19'
        with patch('vision.ocr',side_effect=read) as ocr:
            self.assertEqual(vision.timer_seconds(np.zeros((960,1280,3),np.uint8),unit=81),119)
        self.assertEqual(ocr.call_count,12)


class ZoomFeatureReuseTests(unittest.TestCase):
    def setUp(self):
        self.scene=vision.Scene([],[(60,90),(140,140),(220,120)],(10,10,270,270),[None]*3,None,None)
        rng=np.random.default_rng(315)
        original=rng.integers(0,256,(280,280,3),dtype=np.uint8)
        self.images=[cv2.warpAffine(original,cv2.getRotationMatrix2D((140,140),0,scale),
                                   (280,280),borderMode=cv2.BORDER_REFLECT)
                     for scale in (1.,1.04,1.08,1.12)]

    def test_consecutive_feature_reuse_is_exact_and_bounded(self):
        tracker=ZoomMotionTracker()
        expected=[vision.measure_board_motion(a,b,self.scene.board,
                    texture_mask=board_texture_mask(self.scene))
                  for a,b in zip(self.images,self.images[1:])]
        self.assertTrue(all(expected))
        detector=cv2.SIFT_create(nfeatures=1800)
        class CountingDetector:
            calls=0
            def detectAndCompute(self,*args):
                self.calls+=1
                return detector.detectAndCompute(*args)
        counted=CountingDetector()
        with patch('vision.cv2.SIFT_create',return_value=counted), \
             patch('live_atlas_capture.board_texture_mask',wraps=board_texture_mask) as mask:
            for index,(a,b) in enumerate(zip(self.images,self.images[1:])):
                self.assertEqual(tracker.measure(a,b,self.scene),expected[index])
                self.assertEqual(len(tracker.features),1)
                self.assertIs(next(iter(tracker.features.values()))[0],b)
            mask.assert_called_once()
            self.assertEqual(counted.calls,4)  # 4 unique frames, previously 6
        tracker.clear()
        self.assertEqual(tracker.features,{})
        self.assertIsNone(tracker.mask)

    def test_changed_geometry_invalidates_features_and_mask(self):
        tracker=ZoomMotionTracker()
        before,after=self.images[:2]
        tracker.measure(before,after,self.scene)
        for scene in (replace(self.scene,board=(12,10,272,270)),
                      replace(self.scene,markers=[(62,90),(142,140),(222,120)]),
                      replace(self.scene,cards=[(10,10,30,30)])):
            with self.subTest(scene=scene):
                expected=vision.measure_board_motion(after,self.images[2],scene.board,
                           texture_mask=board_texture_mask(scene))
                self.assertEqual(tracker.measure(after,self.images[2],scene),expected)
                self.assertEqual(len(tracker.features),1)

    def test_failed_registration_does_not_accumulate_captures(self):
        tracker=ZoomMotionTracker()
        for _ in range(5):
            before=np.zeros((280,280,3),np.uint8);after=before.copy()
            self.assertIsNone(tracker.measure(before,after,self.scene))
            self.assertEqual(len(tracker.features),1)
            self.assertIs(next(iter(tracker.features.values()))[0],after)


if __name__=='__main__':unittest.main()
