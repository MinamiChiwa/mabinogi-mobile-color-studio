"""Measured period at fractional scaling and actual proposal endpoint colors."""
import unittest
from types import SimpleNamespace
import cv2,numpy as np

class ScreenshotEndpointTests(unittest.TestCase):
    def test_unknown_endpoints_cannot_displace_a_known_compromise(self):
        from screenshot_search import solve
        from screenshot_prediction import VisibleColorField
        points=[np.column_stack((np.arange(10,111),np.full(101,10))),
            np.array([[150.,10.]]),np.array([[80.,80.]])]
        colors=[np.full((101,3),255,np.uint8),np.zeros((1,3),np.uint8),np.full((1,3),128,np.uint8)]
        image=np.full((170,170,3),240,np.uint8);image[10,10:111]=255;image[10,60]=240
        image[10,150]=0;image[55,105]=128
        masks=np.ones((3,170,170),bool);masks[2]=False;masks[2,55,105]=True
        rules=[dict(enabled=True,colors=[c],exact=i<2,tolerance=8.,priority=i+1)
            for i,c in enumerate(('#FFFFFF','#000000','#808080'))]
        result=solve(points,colors,1000,np.array([[10.,10.],[150.,10.],[80.,80.]]),
            rules,np.eye(3),time_budget=2,sample_at=VisibleColorField(image,masks))
        self.assertTrue(result['candidates'])
        self.assertEqual(result['candidates'][0]['observed_rgb'],[[240]*3,[0]*3,[128]*3])
    def test_single_region_endpoint_quality_is_used_before_partial_retention(self):
        from screenshot_search import solve
        from screenshot_prediction import VisibleColorField
        image=np.full((20,2000,3),240,np.uint8);image[5,1301]=0
        field=VisibleColorField(image,np.ones((2,20,2000),bool))
        points=[np.column_stack((np.arange(1,1801),np.full(1800,5))),np.empty((0,2))]
        rgb=[np.zeros((1800,3),np.uint8),np.empty((0,3),np.uint8)]
        rules=[dict(enabled=i==0,exact=True,colors=['#000000'],tolerance=8.,priority=i+1) for i in range(2)]
        result=solve(points,rgb,10000,np.array([[0.,5.],[10.,5.]]),rules,np.eye(3),time_budget=1,sample_at=field)
        self.assertEqual(result['candidates'][0]['observed_rgb'],[[0,0,0]])
        self.assertEqual(result['candidates'][0]['proposal_rank'][0],0)

    def test_interrupted_field_update_cannot_reuse_trees_for_changed_rows(self):
        from screenshot_prediction import PeriodicColorField
        field=PeriodicColorField(10,2);masks=np.ones((2,3,3),bool)
        field.add(np.zeros((3,3,3),np.uint8),masks,np.eye(3));field.prepare()
        class Cancelled(Exception):pass
        calls=0
        def check():
            nonlocal calls
            calls+=1
            if calls==3:raise Cancelled()
        with self.assertRaises(Cancelled):
            field.add(np.full((3,3,3),255,np.uint8),masks,np.diag([2.,2.,1.]),check)
        values,valid,offset=field(np.array([[[2.,2.],[2.,2.]]]),[0,1])
        self.assertEqual(values[0,0].tolist(),[0]*3)
        self.assertEqual(offset[0,0],0.)

    def test_compact_fractional_period_survives_pixel_resampling(self):
        from screenshot_registration import period_from_image
        rng=np.random.default_rng(33445)
        tile=cv2.GaussianBlur(rng.integers(0,256,(350,350,3),dtype=np.uint8),(0,0),1.)
        tile=np.clip((tile.astype(float)-128)*4+128,0,255).astype(np.uint8)
        image=cv2.resize(np.tile(tile,(2,2,1)),(465,465),interpolation=cv2.INTER_LINEAR)
        scene=SimpleNamespace(board=(0,0,465,465),markers=[(77,340),(232,220),(388,260)],cards=[])
        period,_=period_from_image(image,scene)
        self.assertIsNotNone(period)
        self.assertAlmostEqual(period,232.5,delta=.3)

    def test_nonrepeating_texture_does_not_gain_a_period_from_smoothing(self):
        from screenshot_registration import period_from_image
        image=np.random.default_rng(91566).integers(0,256,(466,466,3),dtype=np.uint8)
        scene=SimpleNamespace(board=(0,0,466,466),markers=[(77,340),(233,220),(388,260)],cards=[])
        period,_=period_from_image(image,scene)
        self.assertIsNone(period)

    def test_third_nearby_dark_site_cannot_claim_the_bright_actual_endpoint(self):
        from screenshot_search import solve
        from screenshot_prediction import VisibleColorField
        image=np.full((110,110,3),220,np.uint8)
        points=[np.array([[10.,10.]]),np.array([[50.,10.]]),np.array([[30.,50.]])]
        for p in points:image[int(p[0,1]),int(p[0,0])]=0
        rules=[dict(enabled=True,colors=['#000000'],exact=True,tolerance=8.,priority=i+1) for i in range(3)]
        field=VisibleColorField(image,np.ones((3,110,110),bool))
        found=solve(points,[np.zeros((1,3),np.uint8)]*3,1000,
            np.array([[10.,10.],[50.,10.],[30.,60.]]),rules,np.eye(3),time_budget=.3,sample_at=field)
        self.assertTrue(found['candidates'])
        for row in found['candidates']:
            source=(np.array([[10.,10.],[50.,10.],[30.,60.]])-row['matrix'][:2,2])@np.linalg.inv(row['matrix'][:2,:2]).T
            expected,valid,offset=field(source[None,...],[0,1,2])
            self.assertEqual(row['observed_rgb'],expected[0].tolist())
            self.assertNotEqual(row['observed_rgb'],[[0,0,0]]*3)
            self.assertNotEqual(row['proposal_rank'][0],0)
            self.assertTrue(row['endpoint_sampled'])

    def test_image_field_never_uses_an_unknown_or_masked_source(self):
        from screenshot_prediction import VisibleColorField
        image=np.full((20,20,3),123,np.uint8);mask=np.ones((2,20,20),bool);mask[1,10,10]=False
        field=VisibleColorField(image,mask)
        colors,valid,offset=field(np.array([[[10.,10.],[10.,10.]],[[30.,30.],[2.,3.]]]),[0,1])
        self.assertEqual(valid.tolist(),[[True,False],[False,True]])
        self.assertEqual(colors[0,0].tolist(),[123]*3)

    def test_color_field_is_complete_even_when_target_pool_is_dark_only(self):
        from screenshot_samples import RawSamples
        image=np.full((50,50,3),240,np.uint8);image[10,10]=0
        rule=dict(enabled=True,colors=['#000000'],exact=True,tolerance=8.,priority=1)
        samples=RawSamples(50,[rule]);samples.add(image,np.ones((1,50,50),bool),np.eye(3))
        self.assertEqual(len(samples.rows[0]),1)
        values,valid,_=samples.color_field(np.array([[[30.,30.]]]),[0])
        self.assertTrue(valid[0,0]);self.assertEqual(values[0,0].tolist(),[240]*3)

    def test_nonperiodic_visible_field_accumulates_new_retry_frames(self):
        from screenshot_prediction import ObservedColorField
        field=ObservedColorField(80)
        first=np.full((10,10,3),240,np.uint8);second=first.copy();second[5,0]=0
        mask=np.ones((1,10,10),bool)
        field.add_frame(first,mask,np.eye(3));pose=np.eye(3);pose[0,2]=-20
        field.add_frame(second,mask,pose)
        colors,valid,offset=field(np.array([[[20.,5.]]]),[0])
        self.assertTrue(valid[0,0]);self.assertEqual(colors[0,0].tolist(),[0,0,0])

    def test_cancelled_visible_tree_build_retries_all_regions(self):
        from screenshot_prediction import ObservedColorField
        field=ObservedColorField(80);image=np.full((10,10,3),90,np.uint8)
        field.add_frame(image,np.ones((2,10,10),bool),np.eye(3))
        class Cancelled(Exception):pass
        calls=0
        def check():
            nonlocal calls
            calls+=1
            if calls==2:raise Cancelled()
        with self.assertRaises(Cancelled):field.prepare(check)
        colors,valid,_=field(np.array([[[5.,5.],[5.,5.]]]),[0,1])
        self.assertTrue(np.all(valid));self.assertTrue(np.all(colors==90))

    def test_nonperiodic_overlapping_phase_prefers_the_finer_actual_observation(self):
        from screenshot_prediction import ObservedColorField
        field=ObservedColorField(80);first=np.full((10,10,3),240,np.uint8);second=first.copy();second[2,2]=0
        mask=np.ones((1,10,10),bool)
        field.add_frame(first,mask,np.eye(3));field.add_frame(second,mask,np.diag([2.,2.,1.]))
        colors,valid,offset=field(np.array([[[1.,1.]]]),[0])
        self.assertTrue(valid[0,0]);self.assertEqual(offset[0,0],0.)
        self.assertEqual(colors[0,0].tolist(),[0]*3)

    def test_local_refinement_evaluates_endpoint_instead_of_nearby_dark_site(self):
        from screenshot_samples import RawSamples
        from screenshot_refinement import local_candidates
        image=np.full((50,50,3),240,np.uint8);image[10,10]=0
        rule=dict(enabled=True,colors=['#000000'],exact=True,tolerance=8.,priority=1)
        samples=RawSamples(50,[rule]);samples.add(image,np.ones((1,50,50),bool),np.eye(3))
        rows=local_candidates(samples,np.array([[30.,30.]]),[rule],np.eye(3),step=.4)
        self.assertTrue(rows)
        self.assertTrue(all(row['observed_rgb']==[[240]*3] for row in rows))

if __name__=='__main__':unittest.main()
