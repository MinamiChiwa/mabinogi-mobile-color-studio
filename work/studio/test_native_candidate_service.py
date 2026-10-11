from native_live.build_adapters import TW_ADAPTER
"""Native retry uses the same IO lifetime and does not publish predictions."""
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from native_live import service
from window_target import WindowTarget


class NativeCandidateServiceTests(unittest.TestCase):
    def test_retry_event_and_callback_keep_original_adapter_and_hide_predictions(self):
        events=[];calls=[]
        def retry():
            calls.append(True)
            return True
        owner=SimpleNamespace(stop=threading.Event(),consume_retry_request=retry,
            event=lambda kind,**data:events.append((kind,data)))
        backend=MagicMock();backend.adapter=TW_ADAPTER
        adapter=SimpleNamespace(input_attempts=0,release=lambda:None)
        target=WindowTarget(20,123,'Game','MabinogiMobile.exe')
        baseline=dict(stop_reason='passive_baseline_collected',capture={'capture_folder':'unused'},
            baseline={'motion':{'settings':{}}},session_deadline_monotonic=100.)
        def loop(io,session,settings,rules,**kwargs):
            self.assertIs(io,adapter)
            self.assertNotIn('candidate_choice',kwargs)
            self.assertTrue(callable(kwargs.get('retry_requested')))
            self.assertTrue(kwargs['retry_requested']())
            kwargs['event'](dict(event='native_candidates',batch_id='same-batch',
                candidates=[dict(id='other',colors=['#101010']*2,deltas=[1.,2.])],region_count=2))
            kwargs['event'](dict(event='native_candidate_closed',batch_id='same-batch',reason='expired'))
            kwargs['event'](dict(event='native_retry_available',enabled=True,effective_deadline=100.))
            kwargs['event'](dict(event='native_retry_reset',status='searching',epoch=1))
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
        self.assertEqual(calls,[True])
        candidates=[data for kind,data in events if kind=='native_candidates']
        self.assertEqual(candidates,[])
        self.assertTrue(any(kind=='native_retry_available' for kind,_ in events))
        self.assertTrue(any(kind=='native_retry_reset' for kind,_ in events))
        backend.close.assert_called_once()


if __name__=='__main__':unittest.main()
