"""The visual atlas keeps exactly two independently sampled material maps."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from analyze_live_atlas import export_maps, quality_gate, validation_summary
from atlas_execution import verify_result, CandidateBatch, Context, execute_candidate
from atlas_masks import material_masks
from atlas_pose_scoring import score_pose
from atlas_similarity import similarity_candidates
from periodic_atlas import PeriodicAtlas, translation_candidates
from replay_archive import evaluate
from single_region_search import run_single_region
from test_single_region_search import FakeIO
from test_atlas_similarity_execution import SimilarityGame


class TwoRegionAtlasTests(unittest.TestCase):
    def test_measured_similarity_converges_at_two_real_markers(self):
        game=SimilarityGame();game.codes=['#112233']*2
        game.ctx=Context('two',(40,80,1280,960),game.ctx.board,((838.5,620),(1087.5,660)))
        rules=[dict(enabled=True,colors=['#112233'],exact=True,tolerance=0.) for _ in range(2)]
        row=dict(id=0,dx=85,dy=-45,angle=43,scale=1.01**-7,accepted=True,
                 maximum=0.,average=0.,colors=['#112233']*2,deltas=[0.]*2)
        batch=CandidateBatch([row],game.ctx,1000.,clock=lambda:0.)
        result=execute_candidate(game,batch,batch.id,0,game.capture(),rules,clock=lambda:0.)
        self.assertTrue(result['accepted']);self.assertTrue(result['verified'])
        self.assertEqual(game.reads,2);self.assertEqual(len(result['marker_errors']),2)
        self.assertLessEqual(max(result['marker_errors']),1.)
        np.testing.assert_allclose(result['actual_pose'],game.pose[:2])
        self.assertEqual(result['actual_colors'],['#112233','#112233'])

    def test_pure_translation_uses_drag_and_verifies_two_regions(self):
        game=SimilarityGame();game.codes=['#112233']*2
        game.ctx=Context('two',(40,80,1280,960),game.ctx.board,((838.5,620),(1087.5,660)))
        rules=[dict(enabled=True,colors=['#112233'],exact=True,tolerance=0.) for _ in range(2)]
        row=dict(id=0,dx=60,dy=-30,angle=0,scale=1,accepted=True,
                 maximum=0.,average=0.,colors=['#112233']*2,deltas=[0.]*2)
        batch=CandidateBatch([row],game.ctx,1000.,clock=lambda:0.)
        result=execute_candidate(game,batch,batch.id,0,game.capture(),rules,clock=lambda:0.)
        self.assertTrue(game.actions);self.assertEqual(set(game.actions),{'drag'})
        self.assertTrue(result['accepted']);self.assertEqual(game.reads,2)
        self.assertEqual(len(result['marker_errors']),2)
        self.assertLessEqual(max(result['marker_errors']),1.)

    def test_one_enabled_target_on_two_region_board_uses_two_hex_slots(self):
        io=FakeIO(color='#000000')
        scene=SimpleNamespace(board=(0,0,300,300),markers=[(75,150),(225,150)],cards=[])
        rules=[dict(enabled=True,colors=['#000000'],exact=True,tolerance=0.),
               dict(enabled=False,colors=[],exact=True,tolerance=0.)]
        result=run_single_region(io,scene,rules,game_deadline=100.)
        self.assertTrue(result['accepted']);self.assertTrue(result['verified'])
        self.assertEqual(result['actual_colors'],['#000000',None])
        self.assertEqual(io.commands,[])
        self.assertEqual([values for values,_ in io.reads],[(True,False),(True,False)])

    def atlas(self):
        atlas=PeriodicAtlas([[32,0],[0,32]],resolution=32,regions=2)
        targets=['#FF0000','#00FF00'];points=np.array([[29.5,6.5],[33.5,6.5]])
        for i,point in enumerate(points):
            image=np.full((32,32,3),100,np.uint8)
            x,y=np.floor(point).astype(int)%32
            image[y,x]=[(255,0,0),(0,255,0)][i]
            masks=np.zeros((2,32,32),bool);masks[i]=True
            atlas.add(image,masks)
        rules=[dict(enabled=True,colors=[color],exact=True,tolerance=0.,priority=i+1)
               for i,color in enumerate(targets)]
        return atlas.snapshot(),rules

    def test_material_masks_exclude_connectors_in_both_actual_halves(self):
        scene=SimpleNamespace(board=(100,100,600,600),markers=[(225,350),(475,450)],cards=[])
        masks=material_masks(scene)
        self.assertEqual(masks.shape,(2,500,500))
        self.assertTrue(masks[0,:,:230].any());self.assertTrue(masks[1,:,270:].any())
        self.assertFalse(masks[0,:,250:].any());self.assertFalse(masks[1,:,:250].any())
        self.assertFalse(masks[:,:,125].any());self.assertFalse(masks[:,:,375].any())

    def test_two_regions_keep_halo_width_at_the_same_board_scale(self):
        scene=SimpleNamespace(board=(100,100,600,600),markers=[(225,350),(475,450)],cards=[])
        masks=material_masks(scene)
        self.assertFalse(masks[0,200,143])
        self.assertTrue(masks[0,200,145])

    def test_translation_and_measured_pose_score_only_actual_regions(self):
        atlas,rules=self.atlas();markers=[[29.5,6.5],[33.5,6.5]]
        rows=translation_candidates(atlas,markers,rules,limit=2)
        self.assertTrue(rows[0]['accepted'])
        self.assertEqual(rows[0]['colors'],['#FF0000','#00FF00'])
        scored=score_pose(atlas,[0,0],[[1,0,0],[0,1,0]],markers,[0,0,64,64],rules)
        self.assertEqual(scored['colors'],['#FF0000','#00FF00'])
        verified=verify_result(dict(rows[0],id=0),scored['colors'],rules)
        self.assertTrue(verified['accepted']);self.assertTrue(verified['verified'])
        self.assertEqual(len(verified['actual_deltas']),2)

    def test_two_point_rotation_and_zoom_predict_no_phantom_third(self):
        atlas,rules=self.atlas()
        rows=similarity_candidates(atlas,[[15.,15.],[15.,18.]],rules,[57.,40.],(64,64),
            scale_bounds=(.7,.8),landing_radius=0.)
        self.assertTrue(rows)
        self.assertTrue(rows[0]['accepted'])
        self.assertEqual(rows[0]['colors'],['#FF0000','#00FF00'])
        self.assertEqual(len(rows[0]['deltas']),2)

    def test_two_region_holdout_validation_and_export_stay_complete(self):
        atlas,_=self.atlas();image=np.full((32,32,3),100,np.uint8)
        masks=np.ones((2,32,32),bool)
        observations=evaluate(atlas,image,masks,[0,0])
        self.assertEqual(len(observations),2)
        summary=validation_summary([dict(prediction=observations)])
        self.assertEqual([row['region'] for row in summary],[1,2])
        self.assertTrue(quality_gate([dict(region=i,coverage=1.) for i in (1,2)],
                                    [dict(coverage=1.,rgb_rmse=0.) for _ in (1,2)])['passed'])
        self.assertFalse(quality_gate([dict(region=i,coverage=1.) for i in (1,2)],
                                     [dict(coverage=1.,rgb_rmse=0.) for _ in (1,2)],
                                     required_regions=[1,2,3])['passed'])
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder);export_maps(out,atlas)
            self.assertTrue((out/'expanded/region-2.png').exists())
            self.assertFalse((out/'region-3.png').exists())
            with np.load(out/'atlas.npz') as saved:self.assertEqual(saved['colors'].shape[0],2)
            from atlas_trial import load_atlas
            self.assertEqual(load_atlas(out/'atlas.npz').regions,2)

    def test_resampled_reconstruction_keeps_two_materials_separate(self):
        atlas=PeriodicAtlas([[8,0],[0,8]],resolution=8,regions=2)
        image=np.zeros((8,16,3),np.uint8);image[:,:8]=(255,0,0);image[:,8:]=(0,255,0)
        masks=np.zeros((2,8,16),bool);masks[0,:,:8]=True;masks[1,:,8:]=True
        atlas.add_resampled(image,masks)
        colors,valid,_=atlas.maps()
        self.assertEqual(colors.shape,(2,8,8,3))
        self.assertTrue(valid[0].any());self.assertTrue(valid[1].any())
        self.assertTrue(np.all(colors[0][valid[0]]==[255,0,0]))
        self.assertTrue(np.all(colors[1][valid[1]]==[0,255,0]))


if __name__=='__main__':unittest.main()
