import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from atlas_runtime import Adapter


class CodeReadCacheTests(unittest.TestCase):
    def setUp(self):
        self.scene=SimpleNamespace(cards=[(2,2,10,10),(16,2,10,10),(30,2,10,10)],
                                   markers=[(7,20),(21,20),(35,20)])
        self.image=np.random.default_rng(29).integers(0,256,(30,44,3),dtype=np.uint8)
        self.reader=Adapter(object(),self.scene,'session')
        self.codes=['#ABCDEF','#012345','#FDFDFD']

    def fake_read(self,image,cards,markers,enabled):
        return [value if enabled[i] else None for i,value in enumerate(self.codes)]

    def test_identical_full_cards_reuse_only_successful_checked_codes(self):
        with patch('atlas_runtime.read_codes',side_effect=self.fake_read) as read:
            self.assertEqual(self.reader.read_codes(self.image),self.codes)
            self.assertEqual(self.reader.read_codes(self.image.copy()),self.codes)
        self.assertEqual(read.call_count,1)
        self.assertEqual(self.reader.code_read_stats['calls'],2)
        self.assertEqual(self.reader.code_read_stats['reused_cards'],3)

    def test_one_changed_pixel_in_text_or_swatch_rechecks_affected_card(self):
        for y in (5,10):
            with self.subTest(y=y):
                self.setUp()
                with patch('atlas_runtime.read_codes',side_effect=self.fake_read) as read:
                    self.reader.read_codes(self.image)
                    self.image[y,17,0]^=1
                    self.reader.read_codes(self.image)
                self.assertEqual(read.call_count,2)
                self.assertEqual(read.call_args.kwargs['enabled'],[False,True,False])

    def test_unrelated_pixels_do_not_invalidate_card_but_geometry_does(self):
        with patch('atlas_runtime.read_codes',side_effect=self.fake_read) as read:
            self.reader.read_codes(self.image)
            self.image[20,0]=0
            self.reader.read_codes(self.image)
            self.assertEqual(read.call_count,1)
            self.scene.cards[0]=(3,2,10,10)
            self.reader.read_codes(self.image)
            self.assertEqual(read.call_args.kwargs['enabled'],[True,False,False])

    def test_failed_ocr_is_never_cached(self):
        with patch('atlas_runtime.read_codes',side_effect=[[None]*3,self.codes]) as read:
            self.assertEqual(self.reader.read_codes(self.image),[None]*3)
            self.assertEqual(self.reader.read_codes(self.image),self.codes)
        self.assertEqual(read.call_count,2)

    def test_disabled_regions_stay_disabled_and_sessions_do_not_share_cache(self):
        self.reader.enabled=[True,False,False]
        with patch('atlas_runtime.read_codes',side_effect=self.fake_read) as read:
            self.assertEqual(self.reader.read_codes(self.image),[self.codes[0],None,None])
            self.reader.enabled=[True,True,False]
            self.assertEqual(self.reader.read_codes(self.image),self.codes[:2]+[None])
            self.assertEqual(read.call_args.kwargs['enabled'],[False,True,False])
            other=Adapter(object(),self.scene,'new_session')
            self.assertEqual(other.read_codes(self.image),self.codes)
            self.assertEqual(read.call_args.kwargs['enabled'],[True]*3)

    def test_changed_code_and_swatch_cannot_return_previous_hex(self):
        with patch('atlas_runtime.read_codes',side_effect=self.fake_read):
            self.reader.read_codes(self.image)
            self.image[3:12,3:12]=0
            self.codes[0]='#000000'
            self.assertEqual(self.reader.read_codes(self.image)[0],'#000000')


if __name__=='__main__':unittest.main()
