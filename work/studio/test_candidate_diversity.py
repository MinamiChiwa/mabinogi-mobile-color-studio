import unittest
from atlas_similarity import select_color_candidates


class CandidateDiversityTests(unittest.TestCase):
    def rules(self):
        return [dict(enabled=True,exact=True,colors=['#FFFFFF']) for _ in range(3)]

    def row(self,number,deltas):
        return dict(id=number,colors=['#%06X'%(number*3+i+1) for i in range(3)],
                    deltas=deltas,maximum=max(deltas),average=sum(deltas)/3,
                    accepted=False,dx=number,dy=0)

    def test_single_limit_never_replaces_the_balanced_default(self):
        balanced=self.row(0,[3,3,3]);special=self.row(1,[.1,80,80])
        self.assertEqual(select_color_candidates([special,balanced],self.rules(),1),[balanced])

    def test_deduplication_precedes_limit_and_exact_alternatives_keep_separate_slots(self):
        best=self.row(0,[3,3,3]);duplicates=[dict(best,id=i) for i in range(4)]
        special=[self.row(i+5,[.1 if j==i else 80 for j in range(3)]) for i in range(3)]
        ordinary=[self.row(9+i,[4+i]*3) for i in range(4)]
        result=select_color_candidates(duplicates+ordinary+special,self.rules(),4)
        self.assertEqual(len(result),4);self.assertEqual(result[0]['colors'],best['colors'])
        self.assertEqual({r['id'] for r in result[1:]},{5,6,7})

    def test_lab_zero_without_rgb_match_does_not_claim_exact(self):
        best=self.row(0,[0,0,0]);special=self.row(1,[0,2,2])
        self.assertTrue(select_color_candidates([best,special],self.rules(),2))

    def test_prebind_pool_keeps_reachable_route_with_same_colors(self):
        # A mathematically attractive micro-rotation may be rejected by the
        # integer gesture binder. Keep a distinct translation for the same
        # predicted colours until binding has measured both routes.
        fragile=self.row(0,[1,1,1]);fragile.update(search_space='periodic_similarity',
                                                   angle=.4,scale=1.,dx=0.,dy=0.)
        reachable=self.row(1,[1,1,1]);reachable.update(search_space='periodic_translation',
                                                      angle=0.,scale=1.,dx=7.,dy=0.)
        reachable['colors']=fragile['colors']
        result=select_color_candidates([fragile,reachable],self.rules(),1,
                                       preserve_routes=True)
        self.assertEqual(len(result),2)
        self.assertEqual({row['search_space'] for row in result},
                         {'periodic_similarity','periodic_translation'})

    def test_prebind_pool_is_bounded_per_colour(self):
        rows=[]
        for index in range(40):
            row=self.row(index,[1,1,1]);row.update(angle=index*.1,scale=1.,dx=index,dy=0.)
            row['colors']=['#ABCDEF']*3
            rows.append(row)
        result=select_color_candidates(rows,self.rules(),3,preserve_routes=True)
        self.assertEqual(len(result),4)

    def test_unstable_micro_rotation_does_not_hide_bound_same_colour_translation(self):
        from atlas_bound_route import bind_candidate
        from test_atlas_bound_route import ConstantAtlas,IntegerGame
        game=IntegerGame();atlas=ConstantAtlas()
        rules=[dict(enabled=True,exact=False,colors=['#112233'],tolerance=8)]*3
        base=dict(colors=['#112233']*3,deltas=[0.]*3,accepted=True,maximum=0.,
                  average=0.,landing_maximum=0.,landing_safe=True,landing_radius=1.,
                  exact_matches=0,scale=1.,dy=0.)
        fragile=dict(base,id=0,angle=.4,dx=0.)
        translation=dict(base,id=1,angle=0.,dx=7.)
        proposals=select_color_candidates([fragile,translation],rules,1,preserve_routes=True)
        self.assertEqual([row['id'] for row in proposals],[0,1])
        prepared=[];rejected=[]
        for row in proposals:
            ready,budget=bind_candidate(row,atlas,[0,0],game.ctx.board,game.ctx.markers,
                rules,0,1000,require_stable=True,allow_color_compromise=True)
            if ready is not None:prepared.append(ready)
            else:rejected.append(budget['reason'])
        self.assertEqual(rejected,['unstable_route'])
        result=select_color_candidates(prepared,rules,1)
        self.assertEqual([row['id'] for row in result],[1])


if __name__=='__main__':unittest.main()
