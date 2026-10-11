"""Evidence may correct an unknown-age cap, never a caller's shorter deadline."""
import copy
import inspect
import json
import unittest
from unittest.mock import patch

from native_live.controller import run_goal_loop
from native_live.dye_action_checkpoint import _binding
from test_native_retry import RetryIO


def metadata(io,initial=90.,maximum=117.):
    binding=json.loads(io.binding)
    return dict(deadline_source='existing_active_unknown_age',initial_deadline=initial,
        maximum_deadline=maximum,session_token=binding[0],process_identity=binding[1])


def evidence_frames(cp,first=50.,second=51.,seconds=(67,66)):
    return [dict(hex=cp['client_hex'],screenshot_hex=cp['client_hex'],hex_source=['screenshot']*len(cp['client_hex']),
        screenshot_hex_verified=True,timer_confidence='two_pass_agree',remaining_seconds=value,captured_monotonic=when)
        for when,value in zip((first,second),seconds)]


class DeadlineControllerTests(unittest.TestCase):
    def run_loop(self,io,extension,deadline=90.,bad=False):
        self.assertIn('timer_deadline_extension',inspect.signature(run_goal_loop).parameters)
        original=io.frames;approved=[]
        def frames(label,until):
            rows=original(label,until)
            # A one-second pair costs one second from the first warm sample;
            # the closing budget must reflect that actual observation cost.
            io.t+=1.
            if label=='retry_wait_closed':
                rows=evidence_frames(io.checkpoint(label,until),io.t-1.,io.t,(50,49))
                if bad:rows[0]['remaining_seconds']=117;rows[1]['remaining_seconds']=17
            return rows
        def set_verified(new_end,evidence):approved.append((new_end,copy.deepcopy(evidence)))
        io.frames=frames;io.set_verified_session_deadline=set_verified
        result=run_goal_loop(io,io.session,io.settings,io.rules,engineering_deadline=deadline,
            timer_deadline_extension=extension,retry_requested=lambda:False,clock=io.clock,pause=io.pause)
        return result,approved
    def test_late_verified_pair_corrects_cap_only_inside_same_round_maximum(self):
        io=RetryIO();result,approved=self.run_loop(io,metadata(io))
        self.assertGreater(result['effective_deadline'],90.)
        self.assertLessEqual(result['effective_deadline'],117.)
        self.assertEqual(io.timer_grace_until,31.)
        self.assertEqual(len(approved),1);self.assertTrue(result['accepted'])
        self.assertEqual(result['deadline_extensions'][0]['deadline'],117.)
    def test_short_caller_bound_and_bad_timer_pair_never_extend(self):
        for deadline,bad in ((80.,False),(90.,True)):
            with self.subTest(deadline=deadline,bad=bad):
                io=RetryIO();result,approved=self.run_loop(io,metadata(io),deadline,bad)
                self.assertLessEqual(result['effective_deadline'],deadline)
                self.assertEqual(approved,[])
    def test_missing_io_evidence_boundary_cannot_extend(self):
        io=RetryIO();original=io.frames
        def frames(label,deadline):
            rows=original(label,deadline)
            if label=='retry_wait_closed':
                io.t+=1.;rows=evidence_frames(io.checkpoint(label,deadline),io.t-1.,io.t,(50,49))
            return rows
        io.frames=frames
        result=run_goal_loop(io,io.session,io.settings,io.rules,engineering_deadline=90.,
            timer_deadline_extension=metadata(io),retry_requested=lambda:False,clock=io.clock,pause=io.pause)
        self.assertEqual(result['effective_deadline'],90.)
    def test_independent_pairs_across_reads_extend_only_for_unchanged_actual_pose(self):
        io=RetryIO(scale=.5);original=io.frames;pending=[False];sent=[0];approved=[]
        def frames(label,until):
            rows=original(label,until)
            if label=='retry_1_after':
                rows=evidence_frames(io.checkpoint(label,until),io.t-.02,io.t,(84,84))
            elif label=='retry_2_after':
                rows=evidence_frames(io.checkpoint(label,until),io.t-.02,io.t,(82,82))
            return rows
        def event(row):
            if row['event']=='native_retry_available' and row.get('reason')=='target_observed' and sent[0]<2:
                pending[0]=True;sent[0]+=1;io.t=34. if sent[0]==1 else 35.5
        def requested():
            value=pending[0];pending[0]=False;return value
        io.frames=frames;io.set_verified_session_deadline=lambda end,evidence:approved.append((end,evidence))
        result=run_goal_loop(io,io.session,io.settings,io.rules,engineering_deadline=90.,
            timer_deadline_extension=metadata(io),retry_requested=requested,event=event,clock=io.clock,pause=io.pause)
        self.assertEqual(result['retry_epochs'],2)
        self.assertGreater(result['effective_deadline'],90.)
        self.assertLessEqual(result['effective_deadline'],117.)
        self.assertEqual(len(approved),1)
        pair=approved[0][1]['frames']
        self.assertGreater(pair[1]['captured_monotonic']-pair[0]['captured_monotonic'],.5)
        self.assertEqual([row['remaining_seconds'] for row in pair],[84,82])


class DeadlineIOBoundaryTests(unittest.TestCase):
    def setUp(self):
        from test_native_protected_io import NativeProtectedIOTests
        self.fixture=NativeProtectedIOTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.io=self.fixture.io;self.clock=self.fixture.clock;self.clock.now=51.
        self.io.timer_grace_until=31.
        self.cp=dict(checkpoint_valid=True,cpu_matches=True,client_hex=['#112233']*3,
            binding=_binding(self.io.last_observation))
        self.extension=dict(deadline_source='existing_active_unknown_age',initial_deadline=100.,maximum_deadline=120.,
            session_token=['palette'],process_identity=[42,11,1000,'build'])
        self.io.reference['timer_deadline_extension']=copy.deepcopy(self.extension)
        self.evidence=dict(checkpoint=self.cp,frames=evidence_frames(self.cp),timer_grace_until=31.,
            initial_engineering_deadline=100.,previous_deadline=100.)
    def test_approved_pair_updates_only_the_checked_session_bound(self):
        method=getattr(self.io,'set_verified_session_deadline',None)
        self.assertTrue(callable(method),'Verified deadline IO boundary missing')
        method(114.,self.evidence)
        self.io.check(119.)
        self.assertEqual(self.io.deadline,114.)
        self.assertEqual(self.io.reference['session_deadline_monotonic'],100.)
    def test_unapproved_deadline_and_unbound_evidence_are_rejected(self):
        method=getattr(self.io,'set_verified_session_deadline',None)
        self.assertTrue(callable(method),'Verified deadline IO boundary missing')
        for new_end,mutate in ((119.,lambda e:None),(114.,lambda e:e['frames'][0].update(hex_source=['native_checkpoint']*3))):
            with self.subTest(new_end=new_end):
                evidence=copy.deepcopy(self.evidence);mutate(evidence)
                with self.assertRaises(ValueError):method(new_end,evidence)
        self.io.check(119.);self.assertEqual(self.io.deadline,100.)
    def test_checkpoint_uses_only_accepted_extension_and_requested_phase_deadline(self):
        self.io.set_verified_session_deadline(114.,self.evidence)
        def read(backend,baseline,label,**kwargs):
            self.assertEqual(baseline['session_deadline_monotonic'],113.)
            self.assertEqual(self.io.reference['session_deadline_monotonic'],100.)
            raise RuntimeError('checkpoint stub reached')
        with patch('native_live.project_probe_io.record_action_checkpoint',side_effect=read):
            with self.assertRaisesRegex(RuntimeError,'checkpoint stub reached'):self.io.checkpoint('extended',113.)


if __name__=='__main__':unittest.main()
