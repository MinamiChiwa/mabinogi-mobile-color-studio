"""Packaged research core must work without importing the external workspace."""
from test_support import read_local_fixture_text
from test_support import load_local_palette_session
import importlib,importlib.util,json,unittest
from pathlib import Path


class NativeLivePackageTests(unittest.TestCase):
    def test_missing_screenshot_hex_uses_same_checkpoint_native_hex(self):
        from native_live.project_probe_io import merge_native_hex
        decoded={'hex':['#112233', None, '#AABBCC']}
        result=merge_native_hex(decoded, ['#112233', '#445566', '#AABBCC'])
        self.assertEqual(result['hex'], ['#112233', '#445566', '#AABBCC'])
        self.assertEqual(result['hex_source'], ['screenshot', 'native_checkpoint', 'screenshot'])

    def test_conflicting_screenshot_hex_is_rejected(self):
        from native_live.project_probe_io import merge_native_hex
        with self.assertRaises(ValueError):
            merge_native_hex({'hex':['#FFFFFF', None, '#AABBCC']}, ['#112233', '#445566', '#AABBCC'])

    def test_package_and_preloaded_assets_are_available(self):
        self.assertIsNotNone(importlib.util.find_spec('native_live'),'Native live package is missing')
        timer=importlib.import_module('native_live.probe_timer')
        glyphs=importlib.import_module('native_live.dye_hex_glyphs')
        self.assertTrue(timer.prepare_timer_assets()['preloaded'])
        self.assertTrue(glyphs.prepare_hex_assets()['preloaded'])

    def test_saved_actual_mixed_route_replays_with_owned_planner(self):
        self.assertIsNotNone(importlib.util.find_spec('native_live'),'Native live package is missing')
        planner=importlib.import_module('native_live.same_session_dye_planner')
        from native_palette_scoring import load_session
        from native_input_response import InputGeometry,InputSettings
        from native_palette_search import PoseGrid
        fixture=Path(__file__).parent/'fixtures/native_live/stage68'
        data=json.loads(read_local_fixture_text(fixture/'case.json', encoding='utf-8'))
        session=load_local_palette_session(fixture/'palette');cp=data['initial']
        geometry=InputGeometry(cp['board'],cp['local_size'],'windows_legacy_mouse_pixels')
        settings=InputSettings(**data['settings'])
        context=planner.bind_planning_context(session,cp,geometry,settings,wheel_delta_per_step=1.,
            calibration_evidence=dict(source='stage68_archived',viewport_origin=[0,0],viewport_scale=[1,1],
                backend_during_actions_synchronously_recorded=True))
        frames=[dict(hex=cp['client_hex'],remaining_seconds=110,captured_monotonic=t) for t in (1.,1.1)]
        plan=planner.plan_from_checkpoint(context,cp,frames,data['rules'],PoseGrid((0,0),(0,0),1,1,(1.,),(0.,)),
            now=1.2,engineering_deadline=61.2,time_budget_seconds=6.)
        self.assertEqual(plan['result_classification'],'predicted_exact')
        self.assertEqual({g['kind'] for g in plan['candidate']['input_route']},{'drag','wheel'})
        self.assertFalse(plan['ready_for_input'])

    def test_plan_reference_allows_slow_but_fresh_revalidation(self):
        planner=importlib.import_module('native_live.same_session_dye_planner')
        from native_palette_scoring import load_session
        from native_input_response import InputGeometry,InputSettings
        from native_palette_search import PoseGrid
        fixture=Path(__file__).parent/'fixtures/native_live/stage68'
        data=json.loads(read_local_fixture_text(fixture/'case.json', encoding='utf-8'))
        session=load_local_palette_session(fixture/'palette');cp=data['initial']
        geometry=InputGeometry(cp['board'],cp['local_size'],'windows_legacy_mouse_pixels')
        settings=InputSettings(**data['settings'])
        context=planner.bind_planning_context(session,cp,geometry,settings,wheel_delta_per_step=1.,
            calibration_evidence=dict(source='saved',viewport_origin=[0,0],viewport_scale=[1,1],
                                      backend_during_actions_synchronously_recorded=True))
        frames=[dict(hex=cp['client_hex'],remaining_seconds=None,timer_advisory=True,captured_monotonic=t) for t in (1.,1.1)]
        rules=[dict(enabled=True,exact=True,colors=[c],tolerance=0.) for c in cp['client_hex']]
        plan=planner.plan_from_checkpoint(context,cp,frames,rules,PoseGrid((0,0),(0,0),1,1,(1.,),(0.,)),
            now=1.2,engineering_deadline=200.0,time_budget_seconds=2.)
        fresh=[dict(frame,captured_monotonic=plan['planned_at']+10.+i*.1) for i,frame in enumerate(frames)]
        self.assertTrue(planner.validate_plan_reference(context,plan,cp,fresh,now=plan['planned_at']+10.2,rules=rules)['reference_unchanged'])


if __name__=='__main__':unittest.main()
