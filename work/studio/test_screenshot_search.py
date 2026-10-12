"""Contracts for the replacement screenshot route; no live input."""
import unittest
import numpy as np

class ScreenshotPriorityProposalTests(unittest.TestCase):
    def test_high_priority_near_color_beats_low_priority_exact_proposal(self):
        from screenshot_search import proposal_rank
        from vision import rgb
        active=[dict(enabled=True,exact=True,colors=[target],tolerance=0.,priority=i+1)
                for i,target in enumerate(('#FFFFFF','#000000','#000000'))]
        old=[rgb(code) for code in ('#B59170','#56522E','#000000')]
        near=[rgb(code) for code in ('#E8D9D2','#4A4323','#040404')]
        self.assertLess(proposal_rank(near,active,[0,1,2],[0,0,0],0),
                        proposal_rank(old,active,[0,1,2],[0,0,0],0))

    def test_similar_satisfied_proposal_yields_to_next_region(self):
        from screenshot_search import proposal_rank
        from vision import rgb
        active=[dict(enabled=True,exact=False,colors=['#000000'],tolerance=8.,priority=i+1)
                for i in range(3)]
        a=[rgb(code) for code in ('#101010','#404040','#000000')]
        b=[rgb(code) for code in ('#000000','#808080','#000000')]
        self.assertLess(proposal_rank(a,active,[0,1,2],[0,0,0],0),
                        proposal_rank(b,active,[0,1,2],[0,0,0],0))

def rules(colors,enabled=None):
    return [dict(enabled=True if enabled is None else enabled[i],colors=[c],exact=True,
        tolerance=8,priority=i+1) for i,c in enumerate(colors)]

class ScreenshotSearchTests(unittest.TestCase):
    def test_large_uniform_samples_are_compact_and_keep_all_phases(self):
        from screenshot_samples import RawSamples
        image=np.zeros((600,600,3),np.uint8)
        sample=RawSamples(600,rules(['#000000']))
        sample.add(image,np.ones((1,600,600),bool),np.eye(3))
        points,colors,_=sample.sites(0)
        self.assertEqual(len(points),360000)
        self.assertTrue(np.all(colors==0))
        self.assertLess(sample.storage_bytes,360000*40)

    def test_sampling_stop_checks_interrupt_before_committing_a_region(self):
        from screenshot_samples import RawSamples
        class Stopped(Exception):pass
        calls=[]
        def check():
            calls.append(True)
            if len(calls)==3:raise Stopped()
        sample=RawSamples(600,rules(['#000000']))
        with self.assertRaises(Stopped):
            sample.add(np.zeros((600,600,3),np.uint8),np.ones((1,600,600),bool),np.eye(3),check=check)
        self.assertEqual(len(sample.sites(0)[0]),0)
        self.assertEqual(sample.frames,0)

    def test_same_phase_retains_one_whole_closest_observation(self):
        from screenshot_samples import RawSamples
        sample=RawSamples(10,rules(['#000000']))
        masks=np.ones((1,1,1),bool)
        sample.add(np.array([[[5,0,0]]],np.uint8),masks,np.eye(3))
        sample.add(np.array([[[0,4,0]]],np.uint8),masks,np.eye(3))
        _,colors,_=sample.sites(0)
        self.assertEqual(colors.tolist(),[[0,4,0]])

    def test_large_pair_search_checks_deadline_inside_one_dense_pair_row(self):
        from screenshot_search import _partial
        from unittest.mock import patch
        sites=[np.array([[0.,0.]]),np.column_stack((np.linspace(2,8,512),np.zeros(512)))]
        # The first pair row starts on time, then its deadline expires. It
        # must not build hundreds of proposals before checking again.
        ranked=[]
        def rank(ids,cost):ranked.append(ids);return (cost,)
        with patch('screenshot_search.time.monotonic',side_effect=lambda:11 if ranked else 0):
            found=_partial(sites,100,np.array([[0.,0.],[10.,0.]]),np.eye(3),10,lambda:None,
                rank)
        self.assertTrue(found)
        self.assertLessEqual(len(ranked),257)

    def test_similar_samples_skip_empty_chunks_before_a_lower_material_region(self):
        from screenshot_samples import RawSamples,distances
        configured=rules(['#000000']);configured[0]['exact']=False
        mask=np.zeros((1,400,400),bool);mask[:,250:]=True
        sample=RawSamples(400,configured)
        sample.add(np.zeros((400,400,3),np.uint8),mask,np.eye(3))
        self.assertEqual(len(sample.sites(0)[0]),60000)
        self.assertEqual(distances(np.empty((0,3),np.uint8),configured[0]).shape,(0,))

    def test_raw_single_pixel_target_survives_without_channel_compositing(self):
        from screenshot_samples import RawSamples
        image=np.full((8,8,3),80,np.uint8);image[3,5]=[0,0,0];image[2,4]=[0,0,255]
        sample=RawSamples(8,rules(['#000000','#FFFFFF']))
        masks=np.array([np.ones((8,8),bool)]*2)
        sample.add(image,masks,np.eye(3))
        points,colors,dist=sample.sites(0)
        self.assertEqual(colors[0].tolist(),[0,0,0])
        self.assertEqual(points[0].tolist(),[5,3])

    def test_arbitrary_pair_recovers_wrap_without_a_third_rule(self):
        from screenshot_search import solve
        sites=[np.array([[90.,90.]]),np.array([[10.,90.]])]
        colors=[np.array([[17,34,51]]),np.array([[34,51,68]])]
        markers=np.array([[40.,20.],[80.,20.]])
        current=np.array([[2.,0.,-140.],[0.,2.,-160.],[0.,0.,1.]])
        found=solve(sites,colors,100,markers,rules(['#112233','#223344']),current,time_budget=1)
        best=found['candidates'][0]
        predicted=best['lifted_sites']@best['matrix'][:2,:2].T+best['matrix'][:2,2]
        np.testing.assert_allclose(predicted,markers,atol=1e-6)
        self.assertEqual(best['observed_rgb'],[[17,34,51],[34,51,68]])

    def test_disabled_region_does_not_require_a_target_site(self):
        from screenshot_search import solve
        configured=rules(['#000000','#FFFFFF','#ABCDEF'],[True,False,False])
        found=solve([np.array([[5.,3.]]),np.empty((0,2)),np.empty((0,2))],
            [np.array([[0,0,0]]),np.empty((0,3)),np.empty((0,3))],8,
            np.array([[2.,2.],[5.,2.],[7.,2.]]),configured,np.eye(3),time_budget=.2)
        self.assertTrue(found['candidates'])
        self.assertEqual(found['candidates'][0]['active_indices'],[0])

    def test_missing_low_priority_region_does_not_hide_available_joint_pair(self):
        from screenshot_search import solve
        configured=rules(['#000000','#000000','#FF0000'])
        found=solve(
            [np.array([[5.,3.]]),np.array([[15.,3.]]),np.empty((0,2))],
            [np.array([[0,0,0]]),np.array([[0,0,0]]),np.empty((0,3))],8,
            np.array([[2.,2.],[5.,2.],[7.,2.]]),configured,np.eye(3),time_budget=.2)
        self.assertTrue(found['candidates'])
        self.assertEqual(found['candidates'][0]['active_indices'],[0,1])
        self.assertFalse(found['candidates'][0]['actual_acceptance'])

    def test_only_one_available_region_is_retained_as_a_diagnostic(self):
        from screenshot_search import solve
        configured=rules(['#000000','#FF0000','#00FF00'])
        found=solve(
            [np.array([[5.,3.]]),np.empty((0,2)),np.empty((0,2))],
            [np.array([[0,0,0]]),np.empty((0,3)),np.empty((0,3))],8,
            np.array([[2.,2.],[5.,2.],[7.,2.]]),configured,np.eye(3),time_budget=.2)
        self.assertTrue(found['candidates'])
        self.assertEqual(found['candidates'][0]['active_indices'],[0])

    def test_actual_priority_never_discards_higher_priority_hit_for_average(self):
        from screenshot_search import actual_result
        configured=rules(['#000000']*3)
        high=actual_result(['#000000','#888888','#888888'],configured)
        average=actual_result(['#010101','#010101','#010101'],configured)
        self.assertLess(high['rank'],average['rank'])
        self.assertFalse(high['accepted'])

    def test_prediction_cannot_make_actual_unreadable_region_accepted(self):
        from screenshot_search import actual_result
        result=actual_result(['#FFFFFF',None],rules(['#FFFFFF']*2))
        self.assertFalse(result['verified']);self.assertFalse(result['accepted'])

    def test_pair_proposal_order_honors_high_priority_before_average(self):
        from screenshot_search import solve
        configured=rules(['#000000','#000000']);configured[1]['priority']=1;configured[0]['priority']=2
        found=solve([np.array([[0.,0.],[40.,0.]]),np.array([[10.,0.],[60.,0.]])],
            [np.array([[0,0,0],[40,40,40]]),np.array([[200,200,200],[0,0,0]])],
            100,np.array([[0.,0.],[50.,0.]]),configured,np.eye(3),time_budget=.5)
        self.assertEqual(found['candidates'][0]['observed_rgb'][1],[0,0,0])

    def test_similar_proposal_satisfaction_uses_each_regions_tolerance(self):
        from screenshot_search import proposal_rank
        configured=rules(['#FFFFFF','#FFFFFF'])
        for r in configured:r.update(exact=False,tolerance=8.)
        configured[1]['tolerance']=3.
        hit=proposal_rank([[255,255,255],[250,250,250]],configured,[0,1],[0,0],0)
        miss=proposal_rank([[255,255,255],[210,210,210]],configured,[0,1],[0,0],0)
        self.assertLess(hit,miss)

    def test_infeasible_pair_preserves_high_priority_exact_hit(self):
        from screenshot_search import solve
        configured=rules(['#000000','#000000'])
        found=solve([np.array([[10.,10.],[15.,10.]]),np.array([[20.,10.],[25.,10.]])],
            [np.array([[0,0,0],[1,1,1]]),np.array([[255,255,255],[0,0,0]])],100,
            np.array([[10.,10.],[20.,10.]]),configured,np.eye(3),time_budget=.5)
        self.assertEqual(found['candidates'][0]['observed_rgb'][0],[0,0,0])

    def test_nearby_gray_cannot_hide_exact_black_third_region(self):
        from screenshot_search import solve
        found=solve([np.array([[20.3,20],[20.,20]]),np.array([[60.,20]]),np.array([[40.,54.641]])],
            [np.array([[0,0,0],[1,1,1]]),np.array([[0,0,0]]),np.array([[0,0,0]])],500,
            np.array([[20.,20],[60.,20],[40.,54.641]]),rules(['#000000']*3),np.eye(3),time_budget=1)
        self.assertEqual(found['candidates'][0]['observed_rgb'],[[0,0,0]]*3)

if __name__=='__main__':unittest.main()
