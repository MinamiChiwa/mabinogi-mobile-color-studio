import unittest
from pathlib import Path
import numpy as np
from planner import joint_plan,decompose_gestures
from vision import Scene,rgb

class JointPlannerTests(unittest.TestCase):
    def test_off_center_pivot_gestures_land_all_three_points(self):
        board=(100,200,700,800);center=np.array([400,500]);pivot=np.array([250,380])
        theta=np.radians(27);scale=1.23
        rotation=np.array([[np.cos(theta),-np.sin(theta)],[np.sin(theta),np.cos(theta)]])
        matrix=scale*rotation;offset=(np.eye(2)-matrix)@pivot
        delta=matrix@center+offset-center
        targets=np.array([[200,440],[400,600],[600,550]],float)
        plan=dict(angle=27,scale=scale,dx=delta[0],dy=delta[1])
        gestures=decompose_gestures(plan,board,targets)
        q=np.array(gestures['rotation_anchor']);z=np.array(gestures['zoom_anchor'])
        points=np.array(gestures['sources'])
        points=(points-q)@rotation.T+q
        points=(points-z)*scale+z+gestures['drag']
        np.testing.assert_allclose(points,targets,atol=1e-8)
        np.testing.assert_allclose(q,pivot,atol=1)
        self.assertGreater(np.linalg.norm(q-center),50)

    def test_outside_fixed_point_uses_safe_pivot_and_translation(self):
        plan=dict(angle=-35,scale=.82,dx=140,dy=-130)
        targets=np.array([[80,100],[200,250],[320,160]],float)
        g=decompose_gestures(plan,(0,0,400,400),targets)
        q=np.array(g['rotation_anchor']);self.assertTrue(np.all((q>=48)&(q<=352)))
        a=np.radians(plan['angle']);rot=np.array([[np.cos(a),-np.sin(a)],[np.sin(a),np.cos(a)]])
        result=((np.array(g['sources'])-q)@rot.T)*plan['scale']+q+g['drag']
        np.testing.assert_allclose(result,targets,atol=1e-8)

    def test_translation_only_decomposition_is_finite(self):
        g=decompose_gestures(dict(angle=0,scale=1,dx=30,dy=-20),(0,0,300,300),[(50,80),(150,170),(250,120)])
        np.testing.assert_allclose(g['drag'],[30,-20])
        self.assertTrue(np.isfinite(g['sources']).all())
    @unittest.skipUnless(Path('work/studio/data/sessions/20260917-124122/wheel.png').exists(), 'Private game capture is not distributed')
    def test_real_three_region_candidate_between_coarse_angles(self):
        from PIL import Image
        from vision import recognize
        im=np.array(Image.open('work/studio/data/sessions/20260917-124122/wheel.png'))
        scene=recognize(im,False)
        rules=[dict(enabled=True,colors=[c],exact=False,tolerance=4) for c in ['#4E647E','#7D746E','#F3B639']]
        plan=joint_plan(im,scene,rules)
        self.assertLessEqual(plan['score'],1)
    def test_recovers_shared_rotation_scale_and_translation(self):
        points=np.array([(55,95),(150,150),(245,205)],float);center=np.array([150,150])
        angle=np.radians(20);scale=1.22
        inv=np.array([[np.cos(angle),np.sin(angle)],[-np.sin(angle),np.cos(angle)]])/scale
        sources=np.rint((points-center-[12,-16])@inv.T+center).astype(int)
        colors=['#E02030','#20E030','#2030E0'];im=np.full((300,300,3),100,np.uint8)
        for (x,y),c in zip(sources,colors):im[y-3:y+4,x-3:x+4]=rgb(c)
        rules=[dict(enabled=True,colors=[c],exact=False,tolerance=4) for c in colors]
        plan=joint_plan(im,Scene([],points,(0,0,300,300),[],110,None),rules)
        self.assertLessEqual(plan['score'],1)
        # Validate the predicted source locations against all three independently.
        a=np.radians(plan['angle']);inv=np.array([[np.cos(a),np.sin(a)],[-np.sin(a),np.cos(a)]])/plan['scale']
        predicted=np.rint((points-center-[plan['dx'],plan['dy']])@inv.T+center).astype(int)
        for (x,y),c in zip(predicted,colors):self.assertEqual(tuple(im[y,x]),rgb(c))

    def test_two_matching_regions_do_not_hide_bad_third(self):
        im=np.full((300,300,3),128,np.uint8)
        rules=[dict(enabled=True,colors=['#808080'],exact=False,tolerance=4)]*2+[dict(enabled=True,colors=['#FF0000'],exact=False,tolerance=4)]
        plan=joint_plan(im,Scene([],[(50,100),(150,150),(250,200)],(0,0,300,300),[],110,None),rules)
        self.assertGreater(plan['score'],1)

if __name__=='__main__':unittest.main()
