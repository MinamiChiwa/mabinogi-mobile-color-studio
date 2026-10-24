import unittest

from analyze_live_atlas import quality_gate


class QualityGateTests(unittest.TestCase):
    def setUp(self):
        self.coverage=[dict(region=1,coverage=.95),dict(region=2,coverage=.95),dict(region=3,coverage=.95)]
        self.validation=[dict(region=1,coverage=.95,rgb_rmse=4),
                         dict(region=2,coverage=.50,rgb_rmse=30),
                         dict(region=3,coverage=.95,rgb_rmse=4)]

    def test_unselected_region_does_not_block_two_color_profile(self):
        gate=quality_gate(self.coverage,self.validation,required_regions=[1,3])
        self.assertTrue(gate['passed'])
        self.assertEqual(gate['required_regions'],[1,3])
        self.assertFalse(next(r for r in gate['regions'] if r['region']==2)['required'])

    def test_three_color_profile_still_requires_all_regions(self):
        gate=quality_gate(self.coverage,self.validation,required_regions=[1,2,3])
        self.assertFalse(gate['passed'])


if __name__ == '__main__':unittest.main()
