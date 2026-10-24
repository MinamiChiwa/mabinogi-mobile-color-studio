"""Local search completion must not be presented as a no-solution proof."""
import unittest
from native_status import result_text


class NativeRefinementStatusTests(unittest.TestCase):
    def text(self,reason):
        return result_text(dict(stop_reason='compromise_observed',verified=True,best_current=True,
            accepted=False,refinement_stop=reason))[1]
    def test_search_budget_stop_is_explained_without_infeasibility(self):
        self.assertIn('搜索时间',self.text('local_search_budget'))
        self.assertIn('无解',self.text('local_search_budget'))
    def test_complete_local_family_does_not_claim_global_exhaustion(self):
        self.assertIn('局部',self.text('local_family_exhausted'))
        self.assertIn('无解',self.text('local_family_exhausted'))
    def test_return_reserve_stop_explains_preserved_current_colors(self):
        self.assertIn('恢复时间',self.text('insufficient_protected_time'))
    def test_english_stop_detail_retains_the_reason(self):
        import i18n
        i18n.set_language('English')
        try:
            self.assertIn('search time',i18n.tr(self.text('local_search_budget')))
            self.assertIn('Return time',i18n.tr(self.text('insufficient_protected_time')))
        finally:i18n.set_language('简体中文')


if __name__=='__main__':unittest.main()
