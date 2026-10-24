import copy
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from native_live import service
from window_target import WindowTarget


class TwoRegionServiceTests(unittest.TestCase):
    def test_visual_fallback_binds_scene_count_before_candidate_build(self):
        from atlas_service import AtlasService,AtlasCallbacks
        seen=[];events=[]
        owner=SimpleNamespace(event=lambda kind,**d:events.append((kind,d)))
        rules=[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.,priority=p) for p in (3,2,1)]
        original=copy.deepcopy(rules)
        def build(capture,effective,**kwargs):
            seen.append(effective)
            return dict(quality_gate={'passed':False})
        callbacks=AtlasCallbacks(acquire=lambda *args,**kwargs:dict(scene=SimpleNamespace(cards=[1,2])),
            build=build,default=lambda *args:None,choice=lambda *args:None)
        AtlasService(callbacks).run(owner,rules)
        self.assertEqual(len(seen[0]),2)
        self.assertEqual(rules,original)
        self.assertEqual(next(d for k,d in events if k=='region_layout')['region_count'],2)

    def run_service(self,rules):
        events=[];calls=[]
        def goal(io,session,settings,effective,**kwargs):
            calls.append(copy.deepcopy(effective))
            return dict(stop_reason='target_observed',verified=True,accepted=True,target_exact=True,
                        actual_colors=['#112233','#445566'],actual_deltas=[0.,0.],actual_input_attempts=0)
        session=dict(pixels=[np.zeros((254,254,3),np.uint8)]*2,picker_uv=[[.25,.5],[.75,.5]],region_count=2)
        baseline=dict(stop_reason='passive_baseline_collected',capture={'capture_folder':'unused'},
                      baseline={'motion':{'settings':{}}},session_deadline_monotonic=100.)
        with tempfile.TemporaryDirectory() as folder:
            owner=SimpleNamespace(folder=Path(folder),stop=threading.Event(),event=lambda kind,**d:events.append((kind,d)))
            with patch.object(service,'resolve_target',return_value=WindowTarget(1,2,'Game','MabinogiMobile.exe')),\
                 patch.object(service,'_prepare',return_value=(SimpleNamespace(close=lambda:None),{})),\
                 patch.object(service,'collect_validation_session',return_value=baseline),\
                 patch.object(service,'load_session',return_value=session),\
                 patch.object(service,'InputSettings',return_value={}),\
                 patch.object(service,'ProjectClosedLoopIO',return_value=SimpleNamespace(input_attempts=0,release=lambda:None)),\
                 patch.object(service,'run_goal_loop',side_effect=goal):
                result=service.run_native_search(owner,rules)
        return result,events,calls

    def test_two_region_session_filters_third_target_without_changing_preferences(self):
        rules=[dict(enabled=True,exact=True,colors=[color],tolerance=0.,priority=p) for color,p in
               [('#112233',3),('#445566',2),('#ABCDEF',1)]]
        original=copy.deepcopy(rules);result,events,calls=self.run_service(rules)
        self.assertTrue(result['accepted'],result.get('error'))
        self.assertEqual(len(calls[0]),2)
        self.assertEqual([r['priority'] for r in calls[0]],[3,2])
        self.assertEqual(rules,original)
        layout=next(d for k,d in events if k=='region_layout')
        self.assertEqual(layout['region_count'],2)
        self.assertEqual(layout['available_regions'],[True,True,False])
        self.assertEqual(result['region_count'],2)

    def test_only_third_enabled_stops_before_sender_with_clear_layout(self):
        rules=[dict(enabled=i==2,exact=True,colors=['#000000'] if i==2 else [],tolerance=0.) for i in range(3)]
        result,events,calls=self.run_service(rules)
        self.assertEqual(calls,[])
        self.assertEqual(result['stop_reason'],'no_available_regions')
        self.assertEqual(result['actual_input_attempts'],0)
        self.assertTrue(any(k=='region_layout' for k,d in events))


if __name__=='__main__':unittest.main()
