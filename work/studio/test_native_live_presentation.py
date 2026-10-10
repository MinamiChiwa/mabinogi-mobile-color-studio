import importlib,importlib.util,unittest


class NativePresentationTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('native_status'),'Native presentation missing')
        return importlib.import_module('native_status')
    def test_predicted_or_unknown_result_never_claims_actual_success(self):
        m=self.module();data=dict(verified=False,accepted=True,stop_reason='target_observed')
        title,body=m.result_text(data)
        self.assertNotIn('已达标',title);self.assertIn('未完成复核',body)
    def test_no_candidate_is_not_presented_as_unreachable(self):
        m=self.module();title,body=m.result_text(dict(verified=True,accepted=False,stop_reason='not_found_in_budget'))
        self.assertIn('未找到',title);self.assertIn('不能据此判断',body)
    def test_exact_and_user_tolerance_have_distinct_result_titles(self):
        m=self.module()
        for exact,expected in ((True,'精确'),(False,'容差')):
            title,body=m.result_text(dict(verified=True,accepted=True,target_exact=exact,stop_reason='target_observed'))
            self.assertIn(expected,title);self.assertIn('手动确认',body)
    def test_verified_unaccepted_compromise_is_labeled_as_unmatched(self):
        m=self.module();title,body=m.result_text(dict(verified=True,accepted=False,
            stop_reason='compromise_observed',outcome='compromise',best_current=True))
        self.assertIn('妥协',title);self.assertIn('未命中',title)
        self.assertIn('手动确认',body)
    def test_a_predicted_compromise_is_not_presented_as_verified(self):
        title,body=self.module().result_text(dict(verified=False,accepted=False,stop_reason='compromise_observed',outcome='compromise'))
        self.assertNotIn('妥协方案',title);self.assertIn('未完成复核',body)
    def test_an_unrestored_better_observation_is_not_labeled_current_best(self):
        title,body=self.module().result_text(dict(verified=True,accepted=False,stop_reason='compromise_observed',
            outcome='compromise',best_current=False))
        self.assertIn('未恢复',body)

    def test_active_palette_error_does_not_tell_user_to_exit_palette(self):
        title,body=self.module().result_text(dict(verified=False,stop_reason='already_active_palette'))
        self.assertIn('绑定',title)
        self.assertNotIn('退出当前染色界面',body)

    def test_internal_error_is_presented_as_diagnostic_failure(self):
        title,body=self.module().result_text(dict(verified=False,stop_reason='internal_error'))
        self.assertIn('内部',title);self.assertIn('诊断',body)


if __name__=='__main__':unittest.main()
