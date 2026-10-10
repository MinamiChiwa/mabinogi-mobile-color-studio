"""Regression for the actual two-black board that rc5 missed."""
from test_support import read_local_fixture_text
from test_support import load_local_palette_session
import copy,json,time,unittest
from pathlib import Path
from native_palette_scoring import load_session,score_native_pose
from native_input_response import InputSettings,InputGeometry
from native_periodic_search import search_periodic_targets
from native_live.controller import run_goal_loop
from test_native_live_controller import FixtureIO


class PeriodicBlackTests(unittest.TestCase):
    def fixture(self,name='periodic_black'):
        folder=Path(__file__).parent/'fixtures/native_live'/name
        data=json.loads(read_local_fixture_text(folder/'case.json', encoding='utf-8'))
        io=FixtureIO();io.case=data;io.cp=data['initial'];io.pose=copy.deepcopy(io.cp['pose'])
        io.session=load_local_palette_session(folder/'palette');io.settings=InputSettings(**data['settings'])
        io.geometry=InputGeometry(io.cp['board'],io.cp['local_size'],'windows_legacy_mouse_pixels')
        last=[time.monotonic()]
        def charged_clock():
            current=time.monotonic();io.t+=current-last[0];last[0]=current
            return io.t
        io.clock=charged_clock
        return io

    def test_rc8_failed_session_reaches_double_black_with_the_production_entry(self):
        io=self.fixture('rc8_double_black');events=[]
        result=run_goal_loop(io,io.session,io.settings,io.case['rules'],
            engineering_deadline=90.,clock=io.clock,event=events.append)
        self.assertTrue(result['accepted'],result.get('error',result['stop_reason']))
        self.assertEqual(result['actual_colors'][:2],['#000000']*2)
        self.assertTrue(any(g['kind']=='rotate' for g in io.actions))
        self.assertEqual(len(result['planning_rounds']),1)
        self.assertEqual(sum(e['event']=='planning' for e in events),1)

    def test_small_rotation_readback_error_reuses_still_exact_suffix(self):
        from native_live.same_session_dye_planner import plan_from_checkpoint
        io=self.fixture('rc8_double_black');perform=io.perform_candidate;changed=[False];calls=[]
        def perturbed(record,*args,**kwargs):
            receipt=perform(record,*args,**kwargs)
            if record['kind']=='rotate' and not changed[0]:
                io.pose['rotation_degrees']+=.0018;changed[0]=True
            return receipt
        def planner(*args,**kwargs):
            calls.append(True)
            return plan_from_checkpoint(*args,**kwargs)
        io.perform_candidate=perturbed
        result=run_goal_loop(io,io.session,io.settings,io.case['rules'],
            engineering_deadline=90.,clock=io.clock,planner=planner)
        self.assertTrue(result['accepted'],result.get('error',result['stop_reason']))
        self.assertEqual(len(calls),1,'Minor rotation error unnecessarily reran full palette search')

    def test_saved_board_has_verified_global_double_black_solutions(self):
        io=self.fixture()
        result=search_periodic_targets(io.session,io.case['rules'],minimum_scale=.5,maximum_scale=3.,
            subpixel_fractions=(0.,.5),time_budget_seconds=4.)
        self.assertTrue(result['site_scan_complete'])
        self.assertTrue(result['pair_lattice_complete'])
        self.assertTrue(result['candidates'])
        for row in result['candidates']:
            self.assertEqual(score_native_pose(io.session,row['native_pose'],io.case['rules'])['colors'][:2],['#000000']*2)

    def test_global_exact_route_is_not_switched_to_a_large_delta_compromise(self):
        io=self.fixture()
        result=run_goal_loop(io,io.session,io.settings,io.case['rules'],
            engineering_deadline=90.,clock=io.clock,max_rounds=12,max_actions=12)
        self.assertTrue(result['accepted'],result.get('error',result['stop_reason']))
        self.assertEqual(result['actual_colors'][:2],['#000000']*2)
        self.assertEqual(result['actual_deltas'][:2],[0.,0.])
        self.assertFalse(result['compromise_selected'])
        self.assertFalse(result['server_confirmation_verified'])
        self.assertTrue(any(g['kind']=='rotate' or max(abs(g['points'][-1][j]-g['points'][0][j]) for j in range(2))>5 for g in io.actions))
        self.assertTrue(any(p.get('periodic_search',{}).get('candidates') for p in result['planning_rounds']))


if __name__=='__main__':unittest.main()
