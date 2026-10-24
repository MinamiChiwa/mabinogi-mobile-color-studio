import unittest
import numpy as np
from color_family import family_penalties, family_priority, family_fields
from candidate_ranking import candidate_order, candidate_quality, candidate_rank
from atlas_execution import verify_result
from vision import rgb, accepted


def rule(color, exact=False, enabled=True, tolerance=8):
    return dict(colors=[color], exact=exact, enabled=enabled, tolerance=tolerance)


class ColorFamilyTests(unittest.TestCase):
    def test_saturated_blue_excludes_recorded_purple_and_magenta_candidates(self):
        # Lab hue differs by only 10-23 degrees for these visibly purple
        # samples. The independent RGB hue envelope must distinguish them.
        values=['#69268F','#A959B0','#A14A9C','#794AC4','#3C469C','#655BC8']
        losses=family_penalties([rgb(value) for value in values],rule('#0000FF'))
        self.assertTrue((losses[:4]>0).all())
        np.testing.assert_array_equal(losses[4:],0)

    def test_blue_purple_boundary_is_checked_at_small_rgb_changes(self):
        # The same hue envelope applies to the centre and landing samples.
        values=['#5A28C0','#5C28C0']
        loss=family_penalties([rgb(value) for value in values],rule('#0000FF'))
        self.assertEqual(loss[0],0)
        self.assertGreater(loss[1],0)

    def test_blue_compromise_cannot_be_grey_green_or_nearly_black(self):
        colors=['#0080FF','#2868C0','#5363AE','#656066','#008000','#000510']
        losses=family_penalties([rgb(v) for v in colors],rule('#0080FF'))
        np.testing.assert_array_equal(losses[:3],0)
        self.assertTrue((losses[3:]>0).all())

    def test_neutrals_preserve_lightness_and_low_chroma_without_hue(self):
        for target,good,bad in (('#FFFFFF','#EEEEEE','#008000'),
                                ('#000000','#151515','#BBBBBB'),
                                ('#888888','#777777','#FFFFFF')):
            with self.subTest(target=target):
                loss=family_penalties([rgb(good),rgb(bad)],rule(target))
                self.assertEqual(loss[0],0)
                self.assertGreater(loss[1],0)

    def test_hue_wrap_uses_shorter_angle(self):
        # LCh hues on opposite sides of 0 degrees, both pink/red.
        losses=family_penalties([rgb('#CB788B')],rule('#C8789E'))
        self.assertEqual(losses[0],0)

    def test_any_allowed_color_and_disabled_regions(self):
        rules=[rule('#FFFFFF'),rule('#0080FF'),rule('#FFFFFF',enabled=False)]
        rules[1]['colors'].append('#008000')
        maximum,average,losses=family_priority([[rgb('#EEEEEE')],[rgb('#008000')],None],rules)
        fields=family_fields(maximum,average,losses,0)
        self.assertTrue(fields['family_consistent'])
        self.assertIsNone(fields['family_penalties'][2])

    def test_family_protection_precedes_exact_hits_and_is_vector_consistent(self):
        rules=[rule('#FFFFFF',True),rule('#FFFFFF',True),rule('#0080FF')]
        source=dict(id=0,colors=['#FFFFFF']*3,deltas=[0]*3)
        grey=dict(verify_result(source,['#FFFFFF','#FFFFFF','#656066'],rules),id=0)
        blue=dict(verify_result(source,['#EEEEEE','#F0F0F0','#2868C0'],rules),id=1)
        rows=[grey,blue]
        self.assertEqual(grey['exact_matches'],2)
        self.assertEqual(blue['exact_matches'],0)
        self.assertLess(candidate_quality(blue),candidate_quality(grey))
        order=candidate_order([r['exact_matches'] for r in rows],
            [r['maximum'] for r in rows],[r['average'] for r in rows],
            [r['accepted'] for r in rows],[False]*2,[0]*2,[0]*2,
            exact_maximum=[r['exact_maximum'] for r in rows],
            exact_average=[r['exact_average'] for r in rows],
            family_maximum=[r['family_maximum'] for r in rows],
            family_average=[r['family_average'] for r in rows])
        self.assertEqual(order.tolist(),[1,0])
        self.assertEqual(sorted(rows,key=candidate_rank)[0]['id'],1)

    def test_acceptance_still_uses_user_tolerance_and_exact_hex(self):
        for tolerance in (0,8,30,90):
            rules=[rule('#0080FF',tolerance=tolerance),rule('#FFFFFF',enabled=False),
                   rule('#FFFFFF',enabled=False)]
            colors=['#2868C0',None,None]
            measured=verify_result(dict(id=0,colors=colors,deltas=[0,None,None]),colors,rules)
            self.assertTrue(measured['family_consistent'])
            self.assertEqual(measured['accepted'],accepted(colors,rules))

    def test_all_supported_target_colors_are_inside_their_own_envelope(self):
        for color in ('#FFFFFF','#000000','#888888','#0080FF','#FF0000','#00FF00',
                      '#FFFF00','#FF00FF','#00FFFF','#E6D9D1','#777A8D'):
            self.assertEqual(family_penalties([rgb(color)],rule(color))[0],0,color)


if __name__=='__main__':unittest.main()
