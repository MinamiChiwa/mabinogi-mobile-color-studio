"""Timer advisory grace follows the checked session's first usable observation."""
import copy
import unittest

from native_live.collect_dye_validation import collect_validation_session
from native_live import session_deadline
from test_native_live_session_budget import PassiveBackend


class Clock:
    def __init__(self):self.now=0.
    def __call__(self):return self.now
    def pause(self,dt):self.now+=dt


class SlowDiscoveryBackend(PassiveBackend):
    def __init__(self,clock,*,new=False):
        super().__init__(not new);self.clock=clock;self.new=new
    def discover(self,*args):
        self.discovers+=1
        if self.new and self.discovers==1:
            self.clock.now=42.
            self.last_discovery_diagnostic=dict(status='class_uninitialized',initial_absence_verified=True,
                scan_complete=False,eligible_addresses=[],first_eligible_seen_monotonic=None,
                scan_started_monotonic=0.,process_identity=self.process_identity())
            return None
        self.clock.now=72. if self.new else 42.
        self.last_discovery_diagnostic=dict(status='complete',scan_complete=True,uniqueness_verified=True,
            eligible_addresses=['0x7b'],first_eligible_seen_monotonic=70. if self.new else 20.,
            scan_started_monotonic=42. if self.new else 0.,process_identity=self.process_identity())
        return 123


class TimerGraceOriginTests(unittest.TestCase):
    def collect(self,new=False):
        clock=Clock();backend=SlowDiscoveryBackend(clock,new=new)
        result=collect_validation_session(backend,session_seconds=110.,dwell_seconds=.1,poll_seconds=.1,
            clock=clock,pause=clock.pause)
        self.assertEqual(result['stop_reason'],'passive_baseline_collected')
        return result,clock
    def checked(self,result,now):
        method=getattr(session_deadline,'verified_timer_grace_until',None)
        self.assertTrue(callable(method),'Bound timer grace validation missing')
        return method(result,session_token=['same'],process_identity=[7,8,9,'fixture'],now=now)
    def test_data3_scan_42_seconds_does_not_restart_grace_at_controller_start(self):
        result,clock=self.collect()
        self.assertEqual(result.get('session_first_seen_monotonic'),20.)
        self.assertEqual(result.get('timer_grace_until'),50.)
        self.assertEqual(self.checked(result,clock()),50.)
        self.assertEqual(result['session_deadline_monotonic'],110.)
        self.assertEqual(result['inputs_sent'],0)
    def test_uninitialized_wait_uses_first_new_board_at_70_not_preparation_at_zero(self):
        result,clock=self.collect(new=True)
        self.assertEqual(result.get('session_first_seen_monotonic'),70.)
        self.assertEqual(self.checked(result,clock()),100.)
        self.assertEqual(result['session_deadline_monotonic'],180.)
    def test_missing_future_nonfinite_stale_and_changed_build_origins_are_rejected(self):
        result,clock=self.collect()
        mutations=[lambda row:row.update(session_first_seen_monotonic=None),
            lambda row:row.update(session_first_seen_monotonic=43.,timer_grace_until=73.),
            lambda row:row.update(session_first_seen_monotonic=float('nan')),
            lambda row:row.update(session_first_seen_monotonic=-100.,timer_grace_until=-70.),
            lambda row:row['capture'].update(process_identity=[7,8,9,'changed-build']),
            lambda row:row['capture'].update(session_token=['previous-board']),
            lambda row:row.setdefault('session_origin_evidence',{}).update(eligible_addresses=['0x456'])]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                bad=copy.deepcopy(result);mutate(bad)
                with self.assertRaises(ValueError):self.checked(bad,clock())
    def test_old_origin_does_not_authorize_controller_for_expired_session(self):
        result,_=self.collect()
        with self.assertRaises(ValueError):self.checked(result,111.)

    def test_origin_never_authorizes_less_than_three_second_game_tail(self):
        result,clock=self.collect()
        result['session_deadline_monotonic']=result['session_first_seen_monotonic']+118.
        with self.assertRaises(ValueError):self.checked(result,clock())
    def test_timer_grace_never_borrows_a_different_process_identity(self):
        result,clock=self.collect()
        method=getattr(session_deadline,'verified_timer_grace_until',None)
        self.assertTrue(callable(method),'Bound timer grace validation missing')
        with self.assertRaises(ValueError):
            method(result,session_token=['same'],process_identity=[8,8,9,'fixture'],now=clock())
    def test_cancelled_capture_preserves_origin_without_producing_validated_baseline(self):
        clock=Clock()
        class CancelledBackend(SlowDiscoveryBackend):
            def capture_validation_bundle(self,*args,**kw):raise InterruptedError('offline cancellation')
        result=collect_validation_session(CancelledBackend(clock),session_seconds=110.,
            clock=clock,pause=clock.pause)
        self.assertEqual(result['stop_reason'],'interrupted')
        self.assertEqual(result['timer_grace_until'],50.)
        self.assertEqual(result['session_first_seen_monotonic'],20.)
        self.assertEqual(result['inputs_sent'],0)
        with self.assertRaises(ValueError):self.checked(result,clock())
    def test_legacy_passive_origin_is_bound_to_active_observation_not_warmup_start(self):
        clock=Clock()
        class LegacySlowBackend(PassiveBackend):
            def discover(self,*args):
                self.clock=clock;clock.now=42.;return 123
        result=collect_validation_session(LegacySlowBackend(True),dwell_seconds=.1,poll_seconds=.1,
            clock=clock,pause=clock.pause)
        self.assertEqual(result['session_first_seen_source'],'active_validation_observation')
        self.assertEqual(result['session_first_seen_monotonic'],42.)
        self.assertEqual(self.checked(result,clock()),72.)
    def test_invalid_discovery_timestamp_never_becomes_a_capture_budget(self):
        for seen in (float('nan'),float('inf'),True,-1.,43.):
            with self.subTest(seen=seen):
                clock=Clock()
                class InvalidTimeBackend(SlowDiscoveryBackend):
                    def discover(self,*args):
                        candidate=super().discover(*args)
                        self.last_discovery_diagnostic['first_eligible_seen_monotonic']=seen
                        return candidate
                    def capture_validation_bundle(self,*args,**kw):
                        raise AssertionError('Invalid provenance reached capture')
                with self.assertRaises(ValueError):
                    collect_validation_session(InvalidTimeBackend(clock),clock=clock,pause=clock.pause)


if __name__=='__main__':unittest.main()
