from unittest.mock import Mock,patch
import unittest
from search_overlay import SearchOverlay


class TwoRegionOverlayTests(unittest.TestCase):
    def test_selected_visual_candidate_displays_only_two_real_color_rows(self):
        overlay=SearchOverlay.__new__(SearchOverlay)
        for name in ('clear_candidates','results','copy','activity','collapse','resize_surface','render'):
            setattr(overlay,name,Mock())
        data=dict(actual_colors=['#112233','#445566'],actual_deltas=[0.,0.],
                  predicted_colors=['#112233','#445566'],predicted_deltas=[0.,0.],
                  maximum=0.,average=0.,accepted=True,verified=True)
        with patch('search_overlay.ct.CTkLabel') as label:
            overlay.show_verification(data)
        texts=[str(call.kwargs.get('text','')) for call in label.call_args_list]
        self.assertEqual(len(texts),3)
        self.assertIn('区域 1',texts[0]);self.assertIn('区域 2',texts[1])
        self.assertFalse(any('区域 3' in text for text in texts))

    def test_layout_event_owns_effective_rules_without_changing_settings(self):
        overlay=SearchOverlay.__new__(SearchOverlay);overlay.render=Mock();overlay._dismissed=False
        rules=[dict(enabled=True,priority=3),dict(enabled=True,priority=1)]
        overlay.handle('region_layout',dict(region_count=2,rules=rules))
        self.assertEqual(len(overlay.rules),2)
        self.assertTrue(overlay.render.called)


if __name__=='__main__':unittest.main()
