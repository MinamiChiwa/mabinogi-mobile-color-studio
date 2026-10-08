import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
from workflow_budget import WorkflowBudget, earliest_deadline
from atlas_live_adapter import build_current, choice_current
from atlas_service import AtlasService, AtlasCallbacks


class BudgetTests(unittest.TestCase):
    def test_operation_keeps_dynamic_return_and_double_read_reserve(self):
        budget=WorkflowBudget(0.,120.)
        self.assertFalse(budget.allow_operation(now=98.,operation_seconds=5.,
            return_seconds=12.,verification_seconds=4.))
        self.assertTrue(budget.allow_operation(now=80.,operation_seconds=5.,
            return_seconds=12.,verification_seconds=4.))
        # Initial positioning is charged before leaving CPU work, too.
        self.assertFalse(budget.allow_operation(now=80.,operation_seconds=5.,
            return_seconds=12.,verification_seconds=4.,positioning_seconds=18.))

    def test_unknown_operation_cost_fails_closed(self):
        budget=WorkflowBudget(0.,120.)
        for cost in (None,float('inf'),float('nan'),-1.,True):
            with self.subTest(cost=cost),self.assertRaises(ValueError):
                budget.allow_operation(now=10.,operation_seconds=cost,
                    return_seconds=1.,verification_seconds=1.)

    def test_binding_reserve_is_enabled_by_default_and_does_no_late_work(self):
        with patch('atlas_live_adapter.time.monotonic',return_value=140), \
             patch('atlas_live_adapter.build_from_capture',return_value=self.scored_report()), \
             patch('atlas_live_adapter.bind_candidate') as bind:
            report=build_current(self.capture(),self.rules())
        bind.assert_not_called()
        self.assertEqual(report['candidates'],[])
        self.assertTrue(report['search_diagnostics']['binding_budget_guard_enabled'])
        self.assertEqual(report['search_diagnostics']['route_binding_stop_reason'],
                         'finish_and_attempt_reserve')

    def test_slow_binding_keeps_the_candidate_already_prepared(self):
        now=[100.]
        capture=self.capture();capture['deadline']=150.;capture['game'].until=150.
        report=self.scored_report()
        report['candidates']=[dict(id=i,dx=0,dy=0) for i in range(2)]
        def bind(row,*args,**kwargs):
            now[0]+=29.
            return dict(row,accepted=False,maximum=10.,average=10.,
                        colors=['#112233']*3),dict(allowed=True)
        with patch('atlas_live_adapter.time.monotonic',side_effect=lambda:now[0]), \
             patch('atlas_live_adapter.build_from_capture',return_value=report), \
             patch('atlas_live_adapter.bind_candidate',side_effect=bind) as binding:
            built=build_current(capture,self.rules())
        self.assertEqual(binding.call_count,1)
        self.assertEqual([row['id'] for row in built['candidates']],[0])
        self.assertEqual(built['search_diagnostics']['route_binding_unprocessed_count'],1)


    def test_manual_wait_is_excluded_and_game_deadline_can_be_earlier(self):
        late=WorkflowBudget(10000,10120)
        # The nominal 60-second target is advisory.  A normal run remains
        # usable until the OCR-derived game countdown expires.
        self.assertEqual(late.deadline,10120)
        self.assertEqual(late.sampling_deadline,10120)
        short=WorkflowBudget(10000,10035)
        self.assertEqual(short.deadline,10035)
        self.assertEqual(short.sampling_deadline,10035)

    def test_nominal_workflow_deadline_is_measurement_only(self):
        budget=WorkflowBudget(10000,10120)
        self.assertEqual(budget.workflow_deadline,10060)
        self.assertEqual(budget.deadline,10120)
        self.assertEqual(budget.exploration_deadline,10105)
        self.assertEqual(budget.finish_deadline,10120)

    def test_action_cost_estimate_must_fit_before_finish_reserve(self):
        budget=WorkflowBudget(100.,220.)
        self.assertEqual(budget.estimate_cost(action_seconds=1,
                                               registration_seconds=2,
                                               verification_seconds=3,
                                               return_seconds=4),10.)
        self.assertTrue(budget.can_start_exploration(now=200.,
                                                     action_seconds=1,
                                                     registration_seconds=1,
                                                     verification_seconds=1,
                                                     return_seconds=1))
        self.assertFalse(budget.can_start_exploration(now=201.,
                                                      action_seconds=1,
                                                      registration_seconds=1,
                                                      verification_seconds=1,
                                                      return_seconds=1))
        with self.assertRaises(ValueError):budget.estimate_cost(action_seconds=-1)

    def test_deadline_override_can_only_shorten(self):
        self.assertEqual(earliest_deadline(None,160,200),160)
        self.assertEqual(earliest_deadline(160,130),130)
        for bad in (float('nan'),float('inf')):
            with self.assertRaises(ValueError):earliest_deadline(160,bad)

    def capture(self):
        g=MagicMock();g.until=160;g.geometry.return_value=(0,0,100,100)
        return dict(game=g,deadline=160,image=None,
                    scene=SimpleNamespace(board=(0,0,100,100),markers=((1,1),)*3))

    def scored_report(self):
        # A live batch now requires an atlas and endpoint-scored candidates.
        atlas=SimpleNamespace(sample=lambda region,points,offset:
                              ([[17,34,51]]*len(points),[True]*len(points)))
        return dict(quality_gate=dict(passed=True),candidates=[dict(id=0,dx=0,dy=0)],
                    runtime=dict(atlas=atlas,capture_offset=[0,0]))

    def rules(self):
        return [dict(enabled=True,exact=False,tolerance=8,colors=['#112233'])]*3

    def test_expired_build_never_publishes_batch(self):
        capture=self.capture()
        with patch('atlas_live_adapter.time.monotonic',side_effect=[150,161]), \
             patch('atlas_live_adapter.build_from_capture',return_value={'candidates':[{'id':0}]}), \
             patch('atlas_live_adapter.CandidateBatch') as batch:
            with self.assertRaisesRegex(RuntimeError,'during build'):build_current(capture,[])
        batch.assert_not_called()

    def test_expired_before_build_does_no_analysis(self):
        with patch('atlas_live_adapter.time.monotonic',return_value=161), \
             patch('atlas_live_adapter.build_from_capture') as build:
            with self.assertRaisesRegex(RuntimeError,'before build'):build_current(self.capture(),[])
        build.assert_not_called()

    def test_build_continues_after_nominal_sixty_second_reference(self):
        capture=self.capture();capture['deadline']=220;capture['game'].until=220
        with patch('atlas_live_adapter.time.monotonic',return_value=161), \
             patch('atlas_live_adapter.build_from_capture',return_value={'candidates':[]}):
            report=build_current(capture,[])
        self.assertEqual(report['selection_deadline'],220)

    def test_build_uses_tightest_limit_for_game_batch_and_report(self):
        for override,expected in ((200,160),(150,150)):
            capture=self.capture()
            with patch('atlas_live_adapter.time.monotonic',return_value=100), \
                 patch('atlas_live_adapter.build_from_capture',return_value=self.scored_report()):
                report=build_current(capture,self.rules(),selection_deadline=override)
            self.assertEqual(capture['game'].until,expected)
            self.assertEqual(report['batch'].deadline,expected)
            self.assertEqual(report['selection_deadline'],expected)

    def test_service_cannot_extend_expired_report_with_context(self):
        owner=MagicMock();batch=MagicMock();batch.deadline=160
        callbacks=AtlasCallbacks(MagicMock(),MagicMock(return_value={
            'quality_gate':{'passed':True},'selection_deadline':160,'batch':batch,
            'candidates':[{'id':0}]}),MagicMock(),MagicMock())
        with patch('atlas_service.time.monotonic',return_value=161):
            result=AtlasService(callbacks).run(owner,[],selection_deadline=500)
        self.assertIsNone(result);callbacks.default.assert_not_called()
        batch.invalidate.assert_called_once()
        self.assertNotIn('atlas_candidates',[c.args[0] for c in owner.event.call_args_list])

    def test_earlier_existing_guard_is_preserved_in_candidate_batch(self):
        capture=self.capture();capture['game'].until=145
        with patch('atlas_live_adapter.time.monotonic',return_value=100), \
             patch('atlas_live_adapter.build_from_capture',return_value=self.scored_report()):
            report=build_current(capture,self.rules(),selection_deadline=200)
        self.assertEqual(report['batch'].deadline,145)
        self.assertEqual(report['selection_deadline'],145)

    def test_expired_choice_never_captures_or_executes(self):
        adapter=MagicMock()
        with patch('atlas_live_adapter.time.monotonic',return_value=161), \
             patch('atlas_live_adapter.execute_candidate') as execute:
            with self.assertRaisesRegex(RuntimeError,'before choice'):
                choice_current(MagicMock(),{'adapter':adapter,'selection_deadline':160},
                               {'id':1},[],selection_deadline=500)
        adapter.capture.assert_not_called();execute.assert_not_called()


if __name__=='__main__':unittest.main()
