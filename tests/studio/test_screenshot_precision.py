"""Mixed exact/similar proposals and independent subpixel motion checks."""
import unittest
from types import SimpleNamespace
import cv2
import numpy as np


def mixed_rules():
    return [dict(enabled=True,colors=[color],exact=i<2,tolerance=8.,priority=i+1)
            for i,color in enumerate(('#FFFFFF','#000000','#808080'))]


class ScreenshotMixedPrecisionTests(unittest.TestCase):
    def test_two_exact_hits_do_not_certify_a_bad_similar_third(self):
        from screenshot_search import actual_result,proposal_rank
        rules=mixed_rules()
        good=[[255,255,255],[0,0,0],[130,130,130]]
        bad=[[255,255,255],[0,0,0],[230,120,30]]
        self.assertLess(proposal_rank(good,rules,[0,1,2],[0,0,0],0),
                        proposal_rank(bad,rules,[0,1,2],[0,0,0],0))
        self.assertFalse(actual_result(['#FFFFFF','#000000','#E6781E'],rules)['accepted'])
        self.assertTrue(actual_result(['#FFFFFF','#000000','#828282'],rules)['accepted'])

    def test_two_exact_anchors_are_not_moved_to_fit_similar_third(self):
        from screenshot_search import solve
        markers=np.array([[40.,30.],[80.,30.],[60.,64.6]])
        sites=[np.array([[20.,20.]]),np.array([[40.,20.]]),np.array([[30.,37.45]])]
        colors=[np.array([[255,255,255]]),np.array([[0,0,0]]),np.array([[128,128,128]])]
        found=solve(sites,colors,100,markers,mixed_rules(),np.eye(3),time_budget=.3)
        row=found['candidates'][0]
        mapped=row['lifted_sites']@row['matrix'][:2,:2].T+row['matrix'][:2,2]
        self.assertLess(np.max(np.linalg.norm(mapped[:2]-markers[:2],axis=1)),1e-8)
        self.assertIn('fixed_exact_pair',row)
        self.assertEqual(row['fixed_exact_pair'],[0,1])

    def test_geometry_retention_uses_target_quality_before_movement_cost(self):
        from screenshot_geometry import solve_joint
        sites=[np.array([[10.,10.],[12.,10.]]),np.array([[50.,10.]]),np.array([[30.,45.]])]
        markers=np.array([[10.,10.],[50.,10.],[30.,45.]])
        def quality(ids,residuals,cost):
            return np.column_stack((ids[:,0]!=1,np.max(residuals,axis=1),cost))
        found=solve_joint(sites,200,markers,current_matrix=np.eye(3),time_budget=.3,
            limit=1,fixed_pair=(0,1),candidate_quality=quality)
        self.assertEqual(int(found['candidates'][0]['site_indices'][0]),1)

    def test_matched_third_color_is_not_thinned_when_anchor_pool_is_small(self):
        from screenshot_search import solve
        from unittest.mock import patch
        y,x=np.mgrid[:8,:8]
        third=np.vstack((np.column_stack((x.ravel(),y.ravel()))*12.5+2,[[30.,37.3]]))
        sites=[np.array([[20.,20.]]),np.array([[40.,20.]]),third]
        colors=[np.array([[255,255,255]]),np.array([[0,0,0]]),
                np.vstack((np.full((64,3),128),[[130,130,130]]))]
        # The CPU deadline expires after the first tier. A known small anchor
        # pool must still examine every matching third-color location there.
        with patch('screenshot_search.time.monotonic',side_effect=[0.,0.,10.,10.]):
            found=solve(sites,colors,100,np.array([[40.,30.],[80.,30.],[60.,64.6]]),
                        mixed_rules(),np.eye(3),time_budget=.3)
        self.assertEqual(found['candidates'][0]['proposal_rank'][0],0)
        self.assertEqual(found['candidates'][0]['observed_rgb'][2],[130,130,130])

    def test_missing_exact_samples_still_produce_a_compromise(self):
        from screenshot_search import solve
        sites=[np.array([[20.,20.]]),np.array([[200.,20.]]),np.array([[100.,37.45]])]
        colors=[np.array([[240,240,240]]),np.array([[15,15,15]]),np.array([[128,128,128]])]
        found=solve(sites,colors,1000,np.array([[40.,30.],[80.,30.],[60.,64.6]]),
                    mixed_rules(),np.eye(3),time_budget=.3)
        self.assertTrue(found['candidates'])
        self.assertNotIn('fixed_exact_pair',found['candidates'][0])
        self.assertFalse(found['candidates'][0]['actual_acceptance'])

    def test_bad_similar_region_does_not_disable_available_exact_anchors(self):
        from screenshot_search import solve
        sites=[np.array([[20.,20.]]),np.array([[40.,20.]]),np.array([[30.,37.45]])]
        colors=[np.array([[255,255,255]]),np.array([[0,0,0]]),np.array([[230,120,30]])]
        found=solve(sites,colors,1000,np.array([[40.,30.],[80.,30.],[60.,64.6]]),
                    mixed_rules(),np.eye(3),time_budget=.3)
        row=found['candidates'][0]
        self.assertEqual(row.get('fixed_exact_pair'),[0,1])
        self.assertLess(max(row['residuals_screen'][:2]),1e-8)
        self.assertNotEqual(row['proposal_rank'][0],0)

    def test_first_candidate_tier_spans_a_uniform_target_plateau(self):
        from screenshot_samples import select_site_indices
        y,x=np.mgrid[:40,:40];points=np.column_stack((x.ravel(),y.ravel()))
        colors=np.full((1600,3),255,np.uint8)
        selected=select_site_indices(points,colors,mixed_rules()[0],40,64)
        self.assertEqual(len(selected),64)
        self.assertGreater(np.ptp(points[selected,1]),30)
        self.assertGreater(np.ptp(points[selected,0]),30)
        self.assertEqual(len(select_site_indices(points,colors,mixed_rules()[0],40,None)),1600)

    def test_raw_samples_prefer_plateau_interior_without_dropping_exact_pixels(self):
        from screenshot_samples import RawSamples
        image=np.zeros((30,30,3),np.uint8);image[4:26,4:26]=255
        samples=RawSamples(30,mixed_rules()[:1])
        samples.add(image,np.ones((1,30,30),bool),np.eye(3))
        points,colors,_=samples.sites(0)
        self.assertEqual(len(points),22*22)
        self.assertGreater(min(points[0]),10)
        self.assertLess(max(points[0]),20)
        self.assertTrue(np.all(colors==255))


class ScreenshotSubpixelRegistrationTests(unittest.TestCase):
    def test_subpixel_refinement_does_not_bias_an_already_correct_seed(self):
        from screenshot_registration import refine_similarity
        rng=np.random.default_rng(41043)
        image=cv2.GaussianBlur(rng.integers(0,256,(701,701,3),dtype=np.uint8),(0,0),1.)
        scene=SimpleNamespace(board=(0,0,701,701),markers=[(100,560),(350,200),(580,260)],cards=[])
        exact=np.eye(3);exact[:2,2]=[.1875,-.15625]
        moved=cv2.warpAffine(image,exact[:2],(701,701),flags=cv2.INTER_LINEAR)
        refined,_=refine_similarity(image,moved,scene,exact)
        points=np.column_stack((scene.markers,np.ones(3)))
        self.assertLess(np.max(np.linalg.norm((points@refined.T-points@exact.T)[:,:2],axis=1)),.03)

    def test_photometric_refinement_recovers_known_similarity_from_noisy_seed(self):
        from screenshot_registration import refine_similarity
        rng=np.random.default_rng(41043)
        image=cv2.GaussianBlur(rng.integers(0,256,(320,360,3),dtype=np.uint8),(0,0),1.)
        scene=SimpleNamespace(board=(0,0,360,320),markers=[(60,260),(180,120),(300,200)],cards=[])
        angle=np.radians(.43);scale=1.006
        exact=np.array([[scale*np.cos(angle),-scale*np.sin(angle),2.35],
                        [scale*np.sin(angle),scale*np.cos(angle),-1.7],[0,0,1.]])
        moved=cv2.warpAffine(image,exact[:2],(360,320),flags=cv2.INTER_LINEAR)
        seed=exact.copy();seed[:2,2]+=[.34,-.27]
        refined,diagnostics=refine_similarity(image,moved,scene,seed)
        points=np.column_stack((scene.markers,np.ones(3)))
        before=np.max(np.linalg.norm((points@seed.T-points@exact.T)[:,:2],axis=1))
        after=np.max(np.linalg.norm((points@refined.T-points@exact.T)[:,:2],axis=1))
        self.assertLess(after,.1)
        self.assertLess(after,before*.3)
        self.assertTrue(diagnostics['improved'])

    def test_flat_or_masked_image_never_invents_subpixel_motion(self):
        from screenshot_registration import refine_similarity
        image=np.full((320,360,3),100,np.uint8)
        scene=SimpleNamespace(board=(0,0,360,320),markers=[(60,260),(180,120),(300,200)],cards=[])
        seed=np.eye(3);seed[0,2]=1.2
        refined,diagnostics=refine_similarity(image,image,scene,seed)
        np.testing.assert_array_equal(refined,seed)
        self.assertFalse(diagnostics['improved'])


class ScreenshotMeasuredRefinementTests(unittest.TestCase):
    def test_final_confirmation_interruption_publishes_an_unverified_result(self):
        from screenshot_live import _publish
        from screenshot_control import Budget,PaletteEnded
        from screenshot_search import actual_result
        from platform_win import Interrupted
        for failure in (PaletteEnded('closed'),Interrupted('stopped')):
            with self.subTest(failure=type(failure).__name__):
                value=actual_result(['#FFFFFF','#000000','#808080'],mixed_rules())
                events=[]
                def observe(*a):raise failure
                c=SimpleNamespace(current=value,best=value,rules=mixed_rules(),actions=[],observations=[],
                    observe=observe,budget=Budget(120,.4),write=lambda *a:None,
                    safe_restore=lambda *a,**kw:dict(verified=False),
                    owner=SimpleNamespace(stop=__import__('threading').Event(),
                        event=lambda *a,**kw:events.append((a,kw))))
                result=_publish(c,'processing_error')
                self.assertEqual(result['outcome'],'unverified')
                self.assertFalse(result['accepted'])
                self.assertTrue(events)

    def test_failed_recovery_does_not_switch_to_another_global_candidate(self):
        from unittest.mock import patch
        from screenshot_live import _search
        from screenshot_search import actual_result
        from screenshot_control import Budget
        rules=mixed_rules();good=actual_result(['#FFFFFF','#010101','#828282'],rules)
        bad=actual_result(['#CCCCCC','#404040','#828282'],rules)
        c=SimpleNamespace(scene=SimpleNamespace(board=(0,0,360,320),markers=[(60,260),(180,120),(300,200)]),
            rules=rules,current=good,best=dict(good,matrix=np.eye(3)),pose=np.eye(3),
            budget=Budget(120,.4),owner=SimpleNamespace(consume_retry_request=lambda:False),
            progress=lambda *a,**kw:None,write=lambda *a:None,check=lambda:None,return_cost=lambda *a,**kw:0.)
        tested=[]
        def move(matrix,*a,**kw):tested.append(matrix);c.pose=matrix;return True
        def read(*a,**kw):c.current=bad;return bad
        c.move_to=move;c.observe=read;c.restore=lambda:bad
        samples=SimpleNamespace(period=100,arrays=lambda **kw:([np.array([[0.,0.]])]*3,[np.array([[0,0,0]])]*3))
        desired=np.eye(3);desired[0,2]=10
        with patch('screenshot_live.solve',return_value=dict(candidates=[dict(matrix=desired)]*2)),patch('screenshot_live._refine'):
            _search(c,samples)
        self.assertEqual(len(tested),1)

    def test_failed_best_recovery_does_not_allow_another_worse_probe(self):
        from unittest.mock import patch
        from screenshot_live import _refine
        from screenshot_search import actual_result
        from screenshot_control import Budget
        rules=mixed_rules();good=actual_result(['#FFFFFF','#010101','#828282'],rules)
        bad=actual_result(['#CCCCCC','#404040','#828282'],rules)
        c=SimpleNamespace(scene=SimpleNamespace(board=(0,0,360,320),markers=[(60,260),(180,120),(300,200)]),
            rules=rules,samples=object(),current=good,best=dict(good,matrix=np.eye(3)),pose=np.eye(3),
            budget=Budget(120,.4),owner=SimpleNamespace(consume_retry_request=lambda:False),
            progress=lambda *a,**kw:None,write=lambda *a:None,check=lambda:None,relocalize=lambda:True,
            return_cost=lambda *a,**kw:0.)
        tested=[]
        def move(matrix,*a,**kw):tested.append(matrix);c.pose=matrix;return True
        def read(*a,**kw):c.current=bad;return bad
        c.move_to=move;c.observe=read;c.restore=lambda:bad
        desired=np.eye(3);desired[0,2]=.4
        with patch('screenshot_live.local_candidates',return_value=[dict(matrix=desired,kind='translate')]):
            _refine(c,max_rounds=2)
        self.assertEqual(len(tested),1)

    def test_failed_confirmation_cannot_be_overridden_by_one_restored_read(self):
        import threading,tempfile,time
        from pathlib import Path
        from unittest.mock import patch
        from screenshot_control import Controller,Budget
        from screenshot_live import _publish
        colors=[['#FFFFFF','#000000','#808080'],['#FFFFFF','#000000','#F0F0F0'],
                ['#FFFFFF','#000000','#808080'],['#FFFFFF','#000000','#F0F0F0']]
        with tempfile.TemporaryDirectory() as folder:
            owner=SimpleNamespace(folder=Path(folder),stop=threading.Event(),event=lambda *a,**kw:None)
            scene=SimpleNamespace(board=(0,0,360,320),markers=[(60,260),(180,120),(300,200)],cards=[])
            c=Controller(owner,None,scene,mixed_rules(),Budget(120,.4));c.check=lambda:None
            def capture(*a):c.frame=np.zeros((320,360,3),np.uint8);return c.frame
            c.capture=capture;c.last_timer=time.monotonic()
            with patch('screenshot_control.read_visible',side_effect=[(v,[]) for v in colors]):
                c.observe('match');c.observe('confirmation');c.observe('return-best-actual')
                result=_publish(c)
            self.assertFalse(result['accepted'])
            self.assertNotEqual(result['outcome'],'matched')

    def test_next_local_trial_starts_from_measured_pose_and_bad_trial_is_restored(self):
        import threading,tempfile
        from pathlib import Path
        from unittest.mock import patch
        from screenshot_live import _refine
        from screenshot_search import actual_result
        from screenshot_control import Budget
        with tempfile.TemporaryDirectory() as folder:
            rules=mixed_rules();original=np.eye(3);samples=object()
            current=actual_result(['#FFFFFF','#010101','#B0B0B0'],rules)
            center=np.eye(3);center[0,2]=.2
            later=np.eye(3);later[0,2]=.55
            tested=[];bases=[];restored=[]
            c=SimpleNamespace(scene=SimpleNamespace(board=(0,0,360,320),markers=[(60,260),(180,120),(300,200)]),
                rules=rules,samples=samples,current=current,best=dict(current,matrix=original),
                pose=original.copy(),pose_known=True,budget=Budget(120,.4),owner=SimpleNamespace(consume_retry_request=lambda:False),
                progress=lambda *a,**kw:None,write=lambda *a:None,check=lambda:None,relocalize=lambda:True,
                return_cost=lambda *a,**kw:0.)
            def choose(*args,**kwargs):
                bases.append(c.pose.copy())
                return [dict(matrix=center if len(bases)==1 else later,kind='translate')]
            def move(matrix,*a,**kw):
                tested.append(np.asarray(matrix).copy());c.pose=np.asarray(matrix).copy();c.pose[0,2]+=.05
                return True
            # A valid final-polish gain cannot worsen the similar third region.
            readings=iter([actual_result(['#FFFFFF','#000000','#B0B0B0'],rules),
                           actual_result(['#CCCCCC','#404040','#828282'],rules)])
            def observe(*a,**kw):
                c.current=next(readings)
                if c.current['rank']<c.best['rank']:c.best=dict(c.current,matrix=c.pose.copy())
                return c.current
            def restore():restored.append(True);c.pose=c.best['matrix'].copy();c.current=c.best;return c.current
            c.move_to=move;c.observe=observe;c.restore=restore
            with patch('screenshot_live.local_candidates',side_effect=choose):
                _refine(c,max_rounds=2)
            self.assertEqual(len(tested),2)
            self.assertAlmostEqual(bases[1][0,2],.25)
            self.assertTrue(restored)
            np.testing.assert_array_equal(c.pose,c.best['matrix'])
            self.assertFalse(c.current['accepted'])


if __name__=='__main__':unittest.main()
