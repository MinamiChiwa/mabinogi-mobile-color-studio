"""Saved rc9 triple-black misses must search intersections and balanced routes."""
from test_support import read_local_fixture_text
from test_support import load_local_palette_session
import copy,json,unittest
from pathlib import Path
from test_native_live_controller import FixtureIO
from native_palette_scoring import load_session
from native_input_response import InputGeometry,InputSettings
from native_live.controller import run_goal_loop
from native_live.compromise import predicted_quality


class NativeTripleBlackTests(unittest.TestCase):
    def io(self):
        folder=Path(__file__).parent/'fixtures/native_live/rc9_triple_black'
        data=json.loads(read_local_fixture_text(folder/'case.json'))
        io=FixtureIO();io.case=data;io.cp=data['initial'];io.pose=copy.deepcopy(io.cp['pose'])
        io.session=load_local_palette_session(folder/'palette');io.settings=InputSettings(**data['settings'])
        io.geometry=InputGeometry(io.cp['board'],io.cp['local_size'],'windows_legacy_mouse_pixels')
        return io

    def test_unmet_triple_exact_retains_a_dark_balanced_route(self):
        io=self.io()
        result=run_goal_loop(io,io.session,io.settings,io.case['rules'],
            engineering_deadline=90.,clock=io.clock,max_rounds=4)
        self.assertTrue(result['verified'],result.get('error'))
        self.assertLess(result['maximum'],10.,result['actual_colors'])
        self.assertTrue(result['best_current'])
        self.assertEqual(result['accepted'],result['actual_colors']==['#000000']*3)

    def test_balanced_route_search_ranks_real_delta_e_before_rgb_exact_miss(self):
        from native_input_compile import native_drag_gesture
        from native_input_route_search import search_native_input_routes
        io=self.io()
        routes=[[native_drag_gesture(io.geometry,io.settings,-2,y).record()] for y in (-8,-10)]
        result=search_native_input_routes(io.session,routes,io.pose,io.geometry,io.settings,io.case['rules'],
            sample_policy='all_recorded_points',wheel_delta_per_step=1.,now=0.,deadline=90.,
            max_depth=0,time_budget_seconds=1.,prediction_quality=lambda p:predicted_quality(p,io.case['rules']))
        self.assertEqual(result['candidates'][0]['input_route'],routes[1])
        self.assertLess(max(result['candidates'][0]['prediction']['deltas']),
            max(result['candidates'][1]['prediction']['deltas']))


if __name__=='__main__':unittest.main()
