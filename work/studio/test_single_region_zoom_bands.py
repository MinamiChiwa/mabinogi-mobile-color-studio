"""Measured evidence, not an assumed absolute zoom, unlocks one wider ring."""
from unittest import TestCase

from single_region_search import QuickSearchLimits, _Search
from test_support import AffineGame, rules, scene


class ZoomBandEvidenceTests(TestCase):
    def search(self, *, exact=True):
        return _Search(AffineGame(), scene(), rules(exact), 120, QuickSearchLimits())

    def test_three_distinct_unimproved_layers_and_both_directions_unlock_one_ring(self):
        search = self.search()
        search.zoom_responses = {-1:.01, 1:.012}
        search.zoom_unimproved_layers = {-.04, -.02, .02}
        search.last_zoom_direction = 1
        search.relative_scale = 1.04
        self.assertGreater(search.next_zoom(), 0)
        self.assertEqual(search.zoom_band, [.75,1.33])
        self.assertEqual(search.zoom_expansions, 1)
        for _ in range(8):search.next_zoom()
        self.assertEqual(search.zoom_expansions, 1)

    def test_failed_or_one_direction_measurements_do_not_unlock_a_ring(self):
        for blocked in (set(), {-1}):
            search = self.search()
            search.zoom_responses[1] = .012
            search.zoom_blocked = blocked
            search.zoom_unimproved_layers = {-.04, -.02, .02}
            search.next_zoom()
            self.assertEqual(search.zoom_expansions, 0)
            self.assertEqual(search.zoom_band, [.85,1.18])

    def test_reliable_native_limit_substitutes_for_the_unavailable_direction(self):
        search = self.search()
        search.zoom_responses[-1] = .01
        search.zoom_native_limits = {1}
        search.zoom_blocked = {1}
        search.zoom_unimproved_layers = {-.04, -.02, -.06}
        search.last_zoom_direction = -1
        self.assertLess(search.next_zoom(), 0)
        self.assertEqual(search.zoom_expansions, 1)

    def test_similarity_and_fewer_than_three_layers_keep_the_first_ring(self):
        for exact, layers in ((False,{-.04,-.02,.02}),(True,{-.04,-.02})):
            search = self.search(exact=exact)
            search.zoom_responses = {-1:.01,1:.012}
            search.zoom_unimproved_layers = layers
            search.next_zoom()
            self.assertEqual(search.zoom_expansions, 0)
