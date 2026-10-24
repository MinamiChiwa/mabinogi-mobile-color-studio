import copy
import sys
import unittest
from profile_store import read_profile
import app
import test_native_ui_hit_testing as hit_testing


@unittest.skipUnless(sys.platform=='win32','Native Tk UI requires Windows')
class TwoRegionUITests(unittest.TestCase):
    def setUp(self):
        self.helper=hit_testing.NativeUIHitTestingTests()
        self.addCleanup(self.helper.doCleanups);self.helper.setUp();self.ui=self.helper.ui

    def test_two_then_three_region_binding_preserves_preferences_and_clears_stale_colors(self):
        original=self.ui.current_profile();self.ui.active_rules=[dict(c.rule(),priority=c.priority.get()) for c in self.ui.cards]
        self.ui.cards[2].current.configure(text='当前颜色  #FFFFFF')
        effective=copy.deepcopy(self.ui.active_rules[:2])
        self.ui.handle_event('region_layout',dict(region_count=2,available_regions=[True,True,False],rules=effective))
        self.assertEqual(self.ui.current_profile(),original)
        self.assertTrue(self.ui.cards[2].enabled.get())
        self.assertFalse(self.ui.cards[2].session_available)
        self.assertIn('不可用',self.ui.cards[2].current.cget('text'))
        self.assertEqual(len(self.ui.active_rules),2)
        self.ui.flush_autosave()
        self.assertEqual(read_profile(app.DATA/'profile.json'),original)
        self.ui.handle_event('region_layout',dict(region_count=3,available_regions=[True]*3,
             rules=[dict(c.rule(),priority=c.priority.get()) for c in self.ui.cards]))
        self.assertTrue(all(c.session_available for c in self.ui.cards))
        self.assertEqual(self.ui.current_profile(),original)
        self.assertEqual(self.helper.errors,[])

    def test_two_region_result_history_ignores_unavailable_third(self):
        self.ui.active_rules=[dict(c.rule(),priority=c.priority.get()) for c in self.ui.cards]
        rules=copy.deepcopy(self.ui.active_rules[:2])
        for r in rules:r['colors']=['#000000']
        self.ui.handle_event('native_result',dict(stop_reason='target_observed',accepted=True,verified=True,target_exact=True,
            region_count=2,rules=rules,actual_colors=['#000000']*2,actual_deltas=[0.]*2,outcome='matched'))
        row=self.ui.history[0]
        self.assertEqual(row['region_count'],2)
        self.assertEqual(row['maximum'],0.)
        self.assertEqual(len(row['regions']),2)
        self.assertIn('不可用',self.ui.cards[2].current.cget('text'))
        self.assertEqual(self.helper.errors,[])


if __name__=='__main__':unittest.main()
