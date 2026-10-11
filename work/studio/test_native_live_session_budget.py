"""New rounds keep a 3 s game tail; unknown active rounds need timer proof."""
import unittest
from native_live.collect_dye_validation import collect_validation_session


class PassiveBackend:
    def __init__(self,existing):self.existing=existing;self.discovers=0
    def process_identity(self):return [7,8,9,'fixture']
    def observe_window_context(self,*args,**kw):
        return dict(extent_one_to_one=True,window=dict(client_size_physical=[1280,960]))
    def discover(self,*args):
        self.discovers+=1
        return 123 if self.existing or self.discovers>1 else None
    def probe(self,*args):return dict(active=True)
    def capture_validation_bundle(self,*args,**kw):
        return dict(session_binding_verified=True,process_identity=self.process_identity(),
            session_token=['same'],capture_folder='offline',pose=dict(position=[0,0],scale=1,rotation_degrees=0),
            cpu_comparison=dict(client_float_hex_equal=True,float_within_tolerance=True))
    def observe_motion(self,*args,**kw):
        return dict(active=True,session_token=['same'],process_identity=self.process_identity(),
            motion=dict(pose=dict(position=[0,0],scale=1,rotation_degrees=0),animators_done=True,binding={},settings={}),
            geometry_diagnostic=dict(rect=dict(cache=dict(local_refresh_pending=False,cache_origin_consistent=True))),
            window_mapping_candidate=dict(client_board_candidate=[0,0,1280,960]),
            window_context=dict(window=dict(client_size_physical=[1280,960])))


class NativeSessionBudgetTests(unittest.TestCase):
    def collect(self,existing,seconds=117.):
        tick=[1.];events=[]
        result=collect_validation_session(PassiveBackend(existing),session_seconds=seconds,dwell_seconds=.1,
            poll_seconds=.1,clock=lambda:tick[0],pause=lambda dt:tick.__setitem__(0,tick[0]+dt),event=events.append)
        self.assertEqual(result['stop_reason'],'passive_baseline_collected')
        return result,events
    def test_new_round_uses_requested_extended_envelope(self):
        result,events=self.collect(False)
        self.assertAlmostEqual(result['session_deadline_monotonic'],118.)
        self.assertFalse(result['existing_active_palette'])
    def test_unknown_age_active_round_is_not_assumed_new(self):
        result,events=self.collect(True)
        self.assertAlmostEqual(result['session_deadline_monotonic'],91.)
        self.assertTrue(result['existing_active_palette'])
        self.assertEqual(result['timer_deadline_extension']['deadline_source'],
                         'existing_active_unknown_age')
        self.assertAlmostEqual(result['timer_deadline_extension']['initial_deadline'],91.)
        self.assertAlmostEqual(result['timer_deadline_extension']['maximum_deadline'],118.)
        self.assertEqual(result['timer_deadline_extension']['process_identity'],[7,8,9,'fixture'])
        self.assertEqual(result['timer_deadline_extension']['session_token'],['same'])
    def test_shorter_caller_deadline_is_not_extended(self):
        for existing in (False,True):
            result,_=self.collect(existing,20.)
            self.assertAlmostEqual(result['session_deadline_monotonic'],21.)
    def test_envelope_cannot_exceed_game_round(self):
        with self.assertRaises(ValueError):self.collect(False,121.)

    def test_full_game_allowance_still_preserves_three_second_tail(self):
        for existing in (False,True):
            result,_=self.collect(existing,120.)
            if existing:
                self.assertAlmostEqual(result['session_deadline_monotonic'],91.)
                self.assertAlmostEqual(result['timer_deadline_extension']['maximum_deadline'],118.)
            else:self.assertAlmostEqual(result['session_deadline_monotonic'],118.)


if __name__=='__main__':unittest.main()
