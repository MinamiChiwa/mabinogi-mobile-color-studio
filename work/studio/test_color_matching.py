"""Color identity must survive search, actual retention and restoration."""
import unittest
import numpy as np

from vision import error, rgb


def rules():
    return [dict(enabled=True, exact=False, colors=[target], tolerance=8., priority=i+1)
            for i, target in enumerate(('#000000', '#FF0000', '#FF0000'))]


class ColorIdentityContractTests(unittest.TestCase):
    def test_rules_without_explicit_priorities_also_use_color_identity(self):
        from hex_refinement import score_codes
        from best_result import ranking
        from native_live.compromise import predicted_quality
        r=[{k:v for k,v in rule.items() if k!='priority'} for rule in rules()]
        orange=['#000000','#F58D16','#E62C2B']
        red=['#000000','#8E0026','#E62C2B']
        self.assertLess(score_codes(red,r)['rank'],score_codes(orange,r)['rank'])
        self.assertLess(ranking(red,r),ranking(orange,r))
        self.assertLess(predicted_quality(score_codes(red,r),r),predicted_quality(score_codes(orange,r),r))

    def test_recorded_red_prefers_dark_red_over_orange_in_every_actual_path(self):
        from best_result import ranking
        from hex_refinement import score_codes
        from native_live.compromise import observed_quality, predicted_quality
        from screenshot_search import actual_result
        r = rules()
        orange = ['#000000', '#F58D16', '#E62C2B']
        red = ['#000000', '#8E0026', '#E62C2B']
        self.assertGreater(error(red[1], r[1]['colors'], False), error(orange[1], r[1]['colors'], False))
        for rank in (ranking, observed_quality,
                     lambda c, r: score_codes(c, r)['rank'],
                     lambda c, r: actual_result(c, r)['rank'],
                     lambda c, r: predicted_quality(score_codes(c, r), r)):
            with self.subTest(rank=rank):
                self.assertLess(rank(red, r), rank(orange, r))

    def test_screenshot_candidate_selection_keeps_red_before_orange(self):
        from screenshot_samples import select_site_indices
        points = np.array([[10., 10.], [20., 20.]])
        colors = np.array([rgb('#F58D16'), rgb('#8E0026')])
        ids = select_site_indices(points, colors, rules()[1], 100., 1)
        self.assertEqual(ids.tolist(), [1])

    def test_refinement_and_recovery_do_not_restore_orange_over_better_red(self):
        from refinement_policy import compare_refinement, recovery_rank
        r = rules()
        orange = ['#000000', '#F58D16', '#E62C2B']
        red = ['#000000', '#8E0026', '#E62C2B']
        self.assertTrue(compare_refinement(red, orange, r)['improved'])
        self.assertFalse(compare_refinement(orange, red, r)['not_worse'])
        self.assertLess(recovery_rank(red, red, r), recovery_rank(orange, red, r))

    def test_satisfied_similar_region_can_yield_inside_its_tolerance(self):
        from refinement_policy import compare_refinement
        r = rules()
        before = ['#000000', '#F58D16', '#E62C2B']
        after = ['#030303', '#8E0026', '#E62C2B']
        self.assertTrue(compare_refinement(after, before, r)['improved'])
        r[0]['exact'] = True
        self.assertFalse(compare_refinement(after, before, r)['not_worse'])

    def test_hue_preference_never_relaxes_acceptance(self):
        from screenshot_search import actual_result
        from hex_refinement import score_codes
        r = rules()
        for c in (['#000000', '#8E0026', '#E62C2B'], ['#000000', '#F58D16', '#E62C2B']):
            self.assertFalse(actual_result(c, r)['accepted'])
            self.assertFalse(score_codes(c, r)['accepted'])
        r[1]['tolerance'] = r[2]['tolerance'] = 60.
        self.assertTrue(score_codes(['#000000', '#8E0026', '#E62C2B'], r)['accepted'])

    def test_scalar_vector_and_alternative_targets_use_one_whole_score(self):
        from color_matching import matching_distances, matching_score
        from region_priority import priority_components, vector_priority_components
        r = rules()
        r[1]['colors'].append('#00FF00')
        samples = ['#F58D16', '#8E0026', '#AB5F44', '#000000', '#555555', '#030001', '#FFCCCA', '#03F001']
        values = np.array([rgb(c) for c in samples])
        scores = matching_distances(values, r[1])
        expected = [min(matching_score(c, dict(colors=[t])) for t in r[1]['colors']) for c in samples]
        np.testing.assert_allclose(scores, expected,rtol=1e-12,atol=1e-10)
        colors = [values]*3
        deltas = [[error(c, rule['colors'], False) for c in samples] for rule in r]
        vector = vector_priority_components(colors, deltas, r)
        for i, code in enumerate(samples):
            np.testing.assert_array_equal(vector[i], priority_components([code]*3, r))

    def test_neutral_targets_are_exactly_unchanged_and_dark_noise_does_not_win(self):
        from color_matching import matching_distances, matching_score
        samples = ['#F58D16', '#8E0026', '#AB5F44', '#000000', '#555555', '#030001', '#FFCCCA']
        for target in ('#000000', '#FFFFFF', '#808080'):
            r = dict(colors=[target])
            np.testing.assert_array_equal(matching_distances([rgb(c) for c in samples], r),
                                          [error(c, [target], False) for c in samples])
        r = dict(colors=['#FF0000'])
        red = matching_score('#8E0026', r)
        for code in ('#F58D16', '#AB5F44', '#000000', '#555555', '#030001', '#FFCCCA'):
            self.assertLess(red, matching_score(code, r), code)

    def test_other_hues_pastels_and_red_wrap(self):
        from color_matching import matching_score
        for target, good, bad in (('#00FF00', '#008E00', '#8DF516'),
                                  ('#0000FF', '#00008E', '#168DF5'),
                                  ('#00FFFF', '#008E8E', '#16F58D'),
                                  ('#FF00FF', '#8E008E', '#F58D16'),
                                  ('#FFCCCA', '#F0C5C4', '#FF0000')):
            self.assertLess(matching_score(good, dict(colors=[target])),
                            matching_score(bad, dict(colors=[target])), target)
        r = dict(colors=['#FF0000'])
        self.assertLess(abs(matching_score('#FF0001', r)-matching_score('#FF0100', r)), 1.)

    def test_color_requirements_and_priority_beat_a_low_priority_red_match(self):
        from best_result import ranking
        r = rules()
        kept = ['#000000', '#8E0026', '#F58D16']
        trade = ['#FFFFFF', '#FF0000', '#FF0000']
        self.assertLess(ranking(kept, r), ranking(trade, r))
        exact = ['#000000', '#FF0000', '#FF0000']
        self.assertLess(ranking(exact, r), ranking(kept, r))
        r[0]['priority'], r[1]['priority'] = 2, 1
        self.assertLess(ranking(trade, r), ranking(kept, r))

    def test_search_scalar_and_vector_endpoint_ranking_agree(self):
        from screenshot_search import proposal_rank, _quality_function
        r = rules()
        colors = [np.array([rgb(c) for c in pair]) for pair in
                  (('#000000', '#000000'), ('#F58D16', '#8E0026'), ('#E62C2B', '#E62C2B'))]
        residuals = np.zeros((2, 3))
        quality = _quality_function(colors, r, [0, 1, 2])(
            np.array([[0, 0, 0], [1, 1, 1]]), residuals, np.zeros(2))
        for i in range(2):
            scalar = proposal_rank([c[i] for c in colors], r, [0, 1, 2], residuals[i], 0)
            np.testing.assert_allclose(quality[i], scalar)
        self.assertLess(tuple(quality[1]), tuple(quality[0]))

    def test_raw_sample_pool_keeps_both_identity_and_original_seeds(self):
        from screenshot_samples import RawSamples
        image=np.empty((12,12,3),np.uint8)
        image[:]=rgb('#F58D16');image[5:8,5:8]=rgb('#8E0026')
        samples=RawSamples(12,[rules()[1]])
        samples.add(image,np.ones((1,12,12),bool),np.eye(3))
        _,colors,_=samples.sites(0)
        np.testing.assert_array_equal(colors[0],rgb('#8E0026'))
        self.assertTrue(np.any(np.all(colors==rgb('#F58D16'),axis=1)))

    def test_no_cycling_between_tolerance_compliant_combinations(self):
        from refinement_policy import compare_refinement
        r=rules();r[2]['enabled']=False
        for tolerance in (8.,60.):
            r[1]['tolerance']=tolerance
            states=[['#000000','#F58D16',None],['#030303','#8E0026',None],
                    ['#010101','#E62C2B',None],['#020202','#FF0000',None]]
            for a in states:
                for b in states:
                    if compare_refinement(a,b,r)['improved']:
                        self.assertFalse(compare_refinement(b,a,r)['improved'])

    def test_candidate_hit_survives_shortlisting_before_any_preference(self):
        from screenshot_samples import select_site_indices
        r=rules()[1];r['exact']=True
        colors=np.array([rgb('#8E0026'),rgb('#FF0000')])
        selected=select_site_indices(np.array([[1.,1.],[2.,2.]]),colors,r,10.,1)
        self.assertEqual(selected.tolist(),[1])

    def test_native_seed_generation_does_not_start_only_from_orange(self):
        from native_target_seeds import target_seed_poses
        image=np.empty((2,2,3),np.uint8);image[:]=rgb('#F58D16');image[1,1]=rgb('#8E0026')
        session=dict(pixels=(image,image,image),picker_uv=[[(i+.5)/3,.5] for i in range(3)],
            color_preserve_ratio=0.,initial_pose=dict(position=[0.,0.],scale=1.,rotation_degrees=0.))
        r=rules();r[0]['colors']=['#FF0000'];r[1]['enabled']=r[2]['enabled']=False
        seeds=target_seed_poses(session,r,pixels_per_region=1,max_candidates=1)
        self.assertEqual(seeds['seeds'][0]['pixel_xy'],[1,1])

    def test_screenshot_tolerance_yield_really_raises_the_retained_anchor(self):
        from test_refinement_retention import ScreenshotRetentionTests
        from refinement_policy import compare_refinement
        r=rules()[:2];r[1]['tolerance']=1.5
        baseline=['#000000','#ED0000'];improved=['#171717','#EE0000']
        stale=['#171717','#ED0000']
        self.assertTrue(compare_refinement(improved,baseline,r)['improved'])
        with ScreenshotRetentionTests().controller(r,iter([baseline,improved,stale])) as c:
            c.refinement_anchor=c.best
            c.observe('improved')
            self.assertEqual(c.best['actual_colors'],improved)
            self.assertEqual(c.refinement_anchor['actual_colors'],improved)
            value=c.observe('regression')
            self.assertFalse(value['refinement_comparison']['not_worse'])
            self.assertEqual(c.best['actual_colors'],improved)


if __name__ == '__main__':
    unittest.main()
