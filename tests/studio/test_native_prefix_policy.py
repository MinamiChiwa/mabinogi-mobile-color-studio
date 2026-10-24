import unittest


class NativePrefixPolicyTests(unittest.TestCase):
    def test_equal_quality_remaining_suffix_is_not_continued(self):
        from native_live.controller import _prefix_is_safe
        self.assertTrue(_prefix_is_safe((True, 0, 0, 1, 0., 0., 41.),
                                        (True, 0, 0, 1, 0., 0., 60.),
                                        (True, 0, 0, 1, 0., 0., 41.)))
        self.assertFalse(_prefix_is_safe((True, 0, 0, 1, 0., 0., 41.),
                                         (True, 0, 0, 1, 0., 0., 41.),
                                         (True, 0, 0, 1, 0., 0., 41.)))


if __name__=='__main__':
    unittest.main()
