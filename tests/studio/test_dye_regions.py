import copy
import unittest
from dye_regions import region_count,session_region_count,bind_region_rules


class DyeRegionTests(unittest.TestCase):
    def test_real_two_region_board_binds_only_existing_left_to_right_slots(self):
        rules=[dict(enabled=True,priority=i+1,colors=['#000000']) for i in range(3)]
        before=copy.deepcopy(rules);bound=bind_region_rules(rules,2)
        self.assertEqual(len(bound),2)
        bound[0]['colors'].append('#FFFFFF')
        self.assertEqual(rules,before)

    def test_disabled_third_on_three_region_board_does_not_change_physical_count(self):
        session=dict(pixels=[1,2,3],picker_uv=[[1/6,.5],[.5,.5],[5/6,.5]])
        self.assertEqual(session_region_count(session),3)
        rules=[dict(enabled=True),dict(enabled=True),dict(enabled=False)]
        self.assertEqual(len(bind_region_rules(rules,3)),3)

    def test_only_unavailable_target_never_sends_a_silent_default(self):
        rules=[dict(enabled=False),dict(enabled=False),dict(enabled=True)]
        with self.assertRaisesRegex(ValueError,'No enabled'):bind_region_rules(rules,2)

    def test_layout_mismatch_and_unsupported_counts_fail(self):
        for n in (1,4,True):
            with self.assertRaises(ValueError):region_count(n)
        with self.assertRaises(ValueError):session_region_count(dict(pixels=[1,2],picker_uv=[1,2,3]))


if __name__=='__main__':unittest.main()
