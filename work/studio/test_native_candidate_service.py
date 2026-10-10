"""Native alternatives remain in the same IO lifetime and selection queue."""
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from native_live import service
from window_target import WindowTarget


class NativeCandidateServiceTests(unittest.TestCase):
    def test_candidate_event_and_choice_callback_keep_original_batch_and_adapter(self):
        events=[];calls=[]
        def choose(batch_id,deadline):
            calls.append((batch_id,deadline))
            return 'other'
        owner=SimpleNamespace(stop=threading.Event(),wait_candidate_choice=choose,
            event=lambda kind,**data:events.append((kind,data)))
        backend=MagicMock()
        adapter=SimpleNamespace(input_attempts=0,release=lambda:None)
        target=WindowTarget(20,123,'Game','MabinogiMobile.exe')
        baseline=dict(stop_reason='passive_baseline_collected',capture={'capture_folder':'unused'},
            baseline={'motion':{'settings':{}}},session_deadline_monotonic=100.)
        def loop(io,session,settings,rules,**kwargs):
            self.assertIs(io,adapter)
            self.assertTrue(callable(kwargs.get('candidate_choice')),
                'The production service must connect the native candidate choice queue')
            self.assertEqual(kwargs['candidate_choice']('same-batch',10.),'other')
            kwargs['event'](dict(event='native_candidates',batch_id='same-batch',
                candidates=[dict(id='other',colors=['#101010']*2,deltas=[1.,2.])],region_count=2))
            kwargs['event'](dict(event='native_candidate_closed',batch_id='same-batch',reason='expired'))
            return dict(stop_reason='target_observed',accepted=True,verified=True,
                actual_colors=['#000000']*2,actual_deltas=[0.,0.])
        with tempfile.TemporaryDirectory() as tmp:
            owner.folder=Path(tmp)
            with patch.object(service,'resolve_target',return_value=target), \
                 patch.object(service,'_prepare',return_value=(backend,{})), \
                 patch.object(service,'collect_validation_session',return_value=baseline), \
                 patch.object(service,'load_session',return_value=dict(region_count=2,pixels=[None]*2,picker_uv=[[.25,.5],[.75,.5]])), \
                 patch.object(service,'InputSettings',return_value={}), \
                 patch.object(service,'ProjectClosedLoopIO',return_value=adapter), \
                 patch.object(service,'run_goal_loop',side_effect=loop):
                result=service.run_native_search(owner,[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.)]*3)
        self.assertEqual(result['stop_reason'],'target_observed')
        self.assertEqual(calls,[('same-batch',10.)])
        candidates=[data for kind,data in events if kind=='native_candidates']
        self.assertEqual(len(candidates),1)
        self.assertEqual(candidates[0]['batch_id'],'same-batch')
        self.assertEqual(candidates[0]['region_count'],2)
        self.assertTrue(any(kind=='native_candidate_closed' for kind,_ in events))
        backend.close.assert_called_once()


if __name__=='__main__':unittest.main()
