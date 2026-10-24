import unittest
from atlas_execution import CandidateBatch, Context, CandidateExpired
from atlas_runner import AtlasController, AtlasPhase


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.context=Context('s',(0,0,900,900),(0,0,900,900),((150,400),(450,400),(750,400)))
        rows=[dict(id=0,dx=20,dy=20,angle=0,scale=1,colors=['#111111']*3,
                   deltas=[1,1,1],accepted=True,maximum=1,average=1),
              dict(id=1,dx=500,dy=0,angle=0,scale=1,colors=['#222222']*3,
                   deltas=[2,2,2],accepted=False,maximum=2,average=2)]
        self.batch=CandidateBatch(rows,self.context,100,clock=lambda:0)
        self.controller=AtlasController(self.batch,self.context.board,lambda:0)

    def test_default_then_choice(self):
        event=self.controller.begin_default()
        self.assertEqual(self.controller.phase,AtlasPhase.DEFAULT_POSITIONING)
        self.assertEqual(event.data['candidate']['id'],0)
        self.batch.commit_default(self.batch.id,self.context,event.data['candidate']['id'])
        self.controller.default_verified({'verified':True,'actual_pose':[[1,0,20],[0,1,20]]})
        event=self.controller.choose(1)
        self.assertEqual(self.controller.phase,AtlasPhase.CHOICE_POSITIONING)
        self.assertEqual(event.data['candidate']['id'],1)
        self.assertEqual(event.data['candidate']['dx'],480)
        self.controller.choice_verified({'verified':True})
        self.assertEqual(self.controller.phase,AtlasPhase.COMPLETE)

    def test_expired_selection_keeps_default(self):
        default=self.controller.begin_default().data['candidate']
        self.batch.commit_default(self.batch.id,self.context,default['id'])
        self.controller.default_verified({'verified':True,'actual_pose':[[1,0,20],[0,1,20]]})
        event=self.controller.selection_expired()
        self.assertEqual(self.controller.phase,AtlasPhase.KEEP_DEFAULT)
        self.assertIn('保持',event.data['message'])
        with self.assertRaises(CandidateExpired):self.controller.choose(1)

    def test_short_time_budget_uses_move_from_default_not_absolute_offset(self):
        rows=[dict(id=0,dx=500,dy=0,angle=0,scale=1,colors=['#111111']*3,
                   deltas=[1,1,1],accepted=True,maximum=1,average=1),
              dict(id=1,dx=0,dy=0,angle=0,scale=1,colors=['#222222']*3,
                   deltas=[2,2,2],accepted=False,maximum=2,average=2)]
        batch=CandidateBatch(rows,self.context,3,clock=lambda:0)
        controller=AtlasController(batch,self.context.board,lambda:0)
        default=controller.begin_default().data['candidate']
        batch.commit_default(batch.id,self.context,default['id'])
        controller.default_verified({'verified':True,'actual_pose':[[1,0,500],[0,1,0]]})
        event=controller.choose(1)
        self.assertEqual(event.kind,'atlas_choice_rejected')
        self.assertEqual(event.data['budget']['steps'],4)
        self.assertEqual(controller.phase,AtlasPhase.KEEP_DEFAULT)

    def test_invalidated_controller_cannot_reenter(self):
        self.controller.invalidate('geometry changed')
        self.assertEqual(self.controller.phase,AtlasPhase.INVALIDATED)
        with self.assertRaises(CandidateExpired):self.controller.begin_default()


if __name__=='__main__':unittest.main()
