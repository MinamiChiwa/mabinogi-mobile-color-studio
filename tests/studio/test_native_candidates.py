"""Native candidate collection and same-session selections using synthetic IO."""
import copy
import unittest
from unittest.mock import patch
import numpy as np

from test_native_two_regions import SyntheticTwoIO, INITIAL, MOVED, rules_for
from native_palette_search import PoseGrid
from native_live.controller import run_goal_loop
from native_live.same_session_dye_planner import plan_from_checkpoint
from native_palette_scoring import score_native_pose
from native_input_response import replay_native_route,_pose
from native_input_compile import native_drag_gesture
from input_gestures import PointerGesture
from native_input_route_search import _needed
from native_live.same_session_dye_planner import audit_candidate_endpoint
from native_live.candidate_selection import (compile_candidate_selection,actual_colors,
    collect_candidate_pool,present_candidates)


class SyntheticThreeIO(SyntheticTwoIO):
    def __init__(self):
        super().__init__()
        third=self.session['pixels'][0].copy();third[:,:,1]=102;third[:,:,2]=119
        self.session.update(pixels=(*self.session['pixels'],third),
            picker_uv=[[1/6,.5],[.5,.5],[5/6,.5]],capture_id='synthetic-three')
    def checkpoint(self,label,deadline):
        self.check(deadline)
        return dict(checkpoint_valid=True,cpu_matches=True,label=label,pose=_pose(self.pose),
            client_hex=score_native_pose(self.session,self.pose,rules_for(['#000000']*3))['colors'],
            binding=self.binding,board=list(self.geometry.board),local_size=list(self.geometry.local_size))


class NativeCandidateTests(unittest.TestCase):
    def no_choice(self,io):
        def choice(batch,deadline):return None
        return choice
    def loop(self,io,*args,**kwargs):
        return run_goal_loop(io,io.session,io.settings,*args,
            engineering_deadline=90.,clock=io.clock,
            pause=lambda seconds:setattr(io,'t',io.t+seconds),**kwargs)
    def plan(self, io, rules):
        cp=io.checkpoint('reference',100.)
        return plan_from_checkpoint(io.context(),cp,io.frames('reference',100.),rules,
            PoseGrid((0.,0.),(0.,0.),1,1,(1.,),(0.,)),now=io.clock(),
            engineering_deadline=90.,time_budget_seconds=3.,clock=io.clock,
            collect_candidates=True)

    def test_already_accepted_native_search_retains_distinct_audited_alternatives(self):
        io=SyntheticTwoIO();plan=self.plan(io,rules_for(INITIAL))
        rows=plan['candidate_pool']
        self.assertGreater(len(rows),1)
        self.assertEqual(len({tuple(r['actual_colors']) for r in rows}),len(rows))
        self.assertLessEqual(len(rows),12)
        self.assertTrue(all(r['endpoint_audit']['full_route_replayed'] for r in rows))
        self.assertTrue(plan['candidate']['prediction']['predicted_accepted'])
        self.assertFalse(plan['candidate']['input_route'])

    def test_current_target_still_publishes_candidates_and_preserves_current_when_not_selected(self):
        io=SyntheticTwoIO();events=[]
        result=self.loop(io,rules_for(INITIAL),event=events.append,candidate_choice=self.no_choice(io))
        ready=next(e for e in events if e['event']=='native_candidate_ready')
        self.assertGreater(len(ready['candidates']),1)
        self.assertEqual(ready['current_colors'],INITIAL)
        self.assertTrue(result['accepted'])
        self.assertEqual(io.actions,[])
        self.assertEqual(io.releases,1)

    def test_explicit_worse_selection_finishes_from_actual_reference_and_changes_final_acceptance(self):
        io=SyntheticTwoIO();events=[];choices=[]
        def choose(batch,deadline):
            if choices:return None
            ready=[e for e in events if e['event']=='native_candidate_ready'][-1]
            row=next(r for r in ready['candidates'] if r['colors']!=INITIAL)
            choices.append(row['colors']);return row['id']
        result=self.loop(io,rules_for(INITIAL),event=events.append,candidate_choice=choose)
        self.assertEqual(result['actual_colors'],choices[0],result.get('error'))
        self.assertFalse(result['accepted'])
        self.assertTrue(result['verified'])
        self.assertTrue(io.actions)
        self.assertTrue(result['candidate_selections'][0]['protection_audit']['every_prefix_has_checked_return'])
        self.assertFalse(result['best_current'])
        self.assertEqual(result['outcome'],'compromise')
        selected=[e for e in events if e['event']=='native_candidate_selected'][-1]
        self.assertEqual(selected['status'],'observed')

    def test_current_and_stale_batch_choices_send_no_input(self):
        io=SyntheticTwoIO();events=[];choices=[]
        def choose(batch,deadline):
            ready=[e for e in events if e['event']=='native_candidate_ready'][-1]
            choices.append(True)
            if len(choices)==1:return 'old-batch-candidate'
            if len(choices)==2:return ready['current_candidate_id']
            return None
        result=self.loop(io,rules_for(INITIAL),event=events.append,candidate_choice=choose)
        self.assertEqual(result['actual_colors'],INITIAL)
        self.assertEqual(io.actions,[])
        self.assertEqual([e['status'] for e in events if e['event']=='native_candidate_selected'],
            ['rejected','current'])

    def test_wait_does_not_extend_session_or_start_partial_selection(self):
        io=SyntheticTwoIO();events=[];calls=[]
        def choose(batch,deadline):
            if calls:return None
            ready=[e for e in events if e['event']=='native_candidate_ready'][-1]
            calls.append(True);io.t=81.5
            return next(r['id'] for r in ready['candidates'] if not r['current'])
        result=self.loop(io,rules_for(INITIAL),event=events.append,candidate_choice=choose)
        self.assertEqual(io.actions,[])
        self.assertEqual(result['actual_colors'],INITIAL)
        self.assertLessEqual(result['effective_deadline'],90.)

    def test_target_found_moves_automatically_then_keeps_the_same_session_for_choices(self):
        io=SyntheticTwoIO();events=[]
        result=self.loop(io,rules_for(MOVED),event=events.append,candidate_choice=self.no_choice(io))
        self.assertTrue(result['accepted'],result.get('error'))
        self.assertEqual(result['actual_colors'],MOVED)
        self.assertTrue(io.actions)
        names=[e['event'] for e in events]
        self.assertLess(names.index('native_candidates'),names.index('action'))
        self.assertLess(names.index('action'),names.index('native_candidate_ready'))
        self.assertEqual(io.releases,1)

    def test_selected_visual_failure_returns_to_actual_anchor_before_offering_again(self):
        io=SyntheticTwoIO();events=[];choices=[];original=io.frames
        def frames(label,deadline):
            if label.startswith('selection_1_') and label.endswith('_after'):
                raise ValueError('Selected endpoint screenshot unavailable')
            return original(label,deadline)
        io.frames=frames
        def choose(batch,deadline):
            if choices:return None
            ready=[e for e in events if e['event']=='native_candidate_ready'][-1]
            choices.append(True);return next(r['id'] for r in ready['candidates'] if not r['current'])
        result=self.loop(io,rules_for(INITIAL),event=events.append,candidate_choice=choose)
        self.assertEqual(result['actual_colors'],INITIAL,result.get('error'))
        self.assertTrue(result['verified'])
        self.assertEqual(result['candidate_selections'][0]['status'],'restored')
        self.assertTrue(any(s['purpose']=='restore_selection' for s in result['steps']))

    def test_two_and_three_region_exact_similar_alternatives_priority_are_sorted_and_small(self):
        for factory in (SyntheticTwoIO,SyntheticThreeIO):
            for similar in (False,True):
                with self.subTest(layout=factory.__name__,similar=similar):
                    io=factory();colors=io.checkpoint('literal',100.)['client_hex']
                    rules=rules_for(colors)
                    for index,rule in enumerate(rules):
                        rule.update(colors=['#FFFFFF',colors[index]],exact=not similar,
                            tolerance=2. if similar else 0.,priority=len(rules)-index)
                    plan=self.plan(io,rules)
                    rows=plan['candidate_pool']
                    self.assertGreater(len(rows),1)
                    self.assertTrue(rows[0]['prediction']['predicted_accepted'])
                    self.assertTrue(all(len(r['actual_colors'])==len(rules) for r in rows))
                    # Acceptance and ordered priority differences are literal
                    # tuple comparisons independent of the planner's rank key.
                    def key(row):
                        p=row['prediction'];order=list(reversed(range(len(rules))))
                        hit=[0 if (p['colors'][i] in rules[i]['colors'] if rules[i]['exact']
                            else p['deltas'][i]<=rules[i]['tolerance']) else 1 for i in order]
                        return (not p['predicted_accepted'],*hit,*(p['deltas'][i] for i in order),
                            max(p['deltas']),sum(p['deltas'])/len(rules))
                    self.assertEqual([key(r) for r in rows],sorted(key(r) for r in rows))

    def test_action_reserve_rejects_whole_selection_before_first_input(self):
        io=SyntheticTwoIO();events=[];choices=[]
        def choose(batch,deadline):
            if choices:return None
            ready=[e for e in events if e['event']=='native_candidate_ready'][-1]
            choices.append(True);return next(r['id'] for r in ready['candidates'] if not r['current'])
        result=self.loop(io,rules_for(INITIAL),event=events.append,candidate_choice=choose,max_actions=1)
        self.assertEqual(io.actions,[])
        self.assertEqual(result['actual_colors'],INITIAL)
        rejected=[e for e in events if e['event']=='native_candidate_selected' and e['status']=='rejected']
        self.assertEqual(rejected[0]['reason'],'insufficient_protected_actions')

    def test_multiple_choices_recompile_from_last_measured_pose_in_one_io_lifecycle(self):
        io=SyntheticTwoIO();events=[];chosen=[]
        def choose(batch,deadline):
            ready=[e for e in events if e['event']=='native_candidate_ready'][-1]
            if len(chosen)==0:
                row=next(r for r in ready['candidates'] if not r['current'])
            elif len(chosen)==1:
                row=next(r for r in ready['candidates'] if r['colors']==INITIAL)
            else:return None
            chosen.append(row['colors']);return row['id']
        result=self.loop(io,rules_for(INITIAL),event=events.append,candidate_choice=choose)
        self.assertEqual(len(result['candidate_selections']),2)
        self.assertEqual(result['candidate_selections'][1]['anchor_colors'],chosen[0])
        self.assertEqual(result['actual_colors'],INITIAL)
        self.assertTrue(result['accepted'])
        self.assertEqual(io.releases,1)
        self.assertEqual(len(result['planning_rounds']),1)

    def test_candidate_wait_rechecks_f9_and_preserves_one_release(self):
        io=SyntheticTwoIO();original=io.check;stopped=[]
        def check(deadline):
            if stopped:raise InterruptedError('F9')
            original(deadline)
        io.check=check
        def choose(batch,deadline):stopped.append(True);return None
        result=self.loop(io,rules_for(INITIAL),candidate_choice=choose)
        self.assertEqual(result['stop_reason'],'interrupted')
        self.assertEqual(io.actions,[])
        self.assertEqual(io.releases,1)
        self.assertFalse(result['verified'])
        self.assertFalse(result['accepted'])
        self.assertEqual(result['last_verified_candidate_colors'],INITIAL)

    def test_candidate_wait_close_reads_changed_board_instead_of_old_verified_colors(self):
        io=SyntheticTwoIO();moved=[]
        def choose(batch,deadline):
            if not moved:
                io.pose=dict(position=[.04,0.],scale=1.,rotation_degrees=0.);moved.append(True)
            return None
        result=self.loop(io,rules_for(INITIAL),candidate_choice=choose)
        self.assertEqual(result['actual_colors'],MOVED)
        self.assertFalse(result['accepted'])
        self.assertEqual(io.actions,[])
        self.assertTrue(result['verified'])

    def test_unknown_selection_input_completion_is_not_retried_or_recovered(self):
        io=SyntheticTwoIO();events=[];chosen=[];original=io.perform_candidate
        def perform(record,label,deadline):
            receipt=original(record,label,deadline);receipt['completed']=False;return receipt
        io.perform_candidate=perform
        def choose(batch,deadline):
            if chosen:return None
            chosen.append(True)
            ready=[e for e in events if e['event']=='native_candidate_ready'][-1]
            return next(r['id'] for r in ready['candidates'] if not r['current'])
        result=self.loop(io,rules_for(INITIAL),event=events.append,candidate_choice=choose)
        self.assertEqual(result['stop_reason'],'input_outcome_unknown')
        self.assertEqual(len(io.actions),1)
        self.assertFalse(result['verified'])
        self.assertFalse(result['accepted'])

    def test_disabled_region_keeps_full_actual_colors_and_none_delta_in_small_presentation(self):
        io=SyntheticThreeIO();colors=io.checkpoint('reference',100.)['client_hex'];rules=rules_for(colors)
        rules[0].update(colors=['#FFFFFF',colors[0]],priority=2)
        rules[1].update(exact=False,colors=[colors[1]],tolerance=2.,priority=1)
        rules[2].update(enabled=False,colors=[])
        plan=self.plan(io,rules)
        presentation=present_candidates('test-batch',plan['candidate_pool'],rules,colors,{},deadline=90.)
        self.assertTrue(all(len(r['colors'])==3 and r['colors'][2] for r in presentation['candidates']))
        self.assertTrue(all(r['deltas'][2] is None for r in presentation['candidates']))
        self.assertTrue(all('input_route' not in r and 'pixels' not in r for r in presentation['candidates']))
        result=self.loop(io,rules,candidate_choice=self.no_choice(io))
        self.assertEqual(result['actual_colors'],colors)
        self.assertIsNone(result['actual_deltas'][2])

    def test_real_scalar_compilation_proves_complete_returns_for_generated_endpoint(self):
        io=SyntheticTwoIO();context=io.context();cp=io.checkpoint('reference',100.)
        route=[native_drag_gesture(io.geometry,io.settings,20,0).record(),
            native_drag_gesture(io.geometry,io.settings,0,20).record()]
        pose=replay_native_route(cp['pose'],route,io.geometry,io.settings,
            wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
        row=dict(input_route=route,final_pose=pose,prediction=score_native_pose(io.session,pose,rules_for(INITIAL)),
            needed=_needed(route,3.,.5),actual_colors=actual_colors(context,pose))
        compiled=compile_candidate_selection(context,cp,rules_for(INITIAL),row,
            deadline=io.clock()+5.,clock=io.clock)
        self.assertEqual(compiled['actual_colors'],['#C82233','#494455'])
        self.assertEqual(len(compiled['prefix_recoveries']),len(compiled['input_route']))
        self.assertTrue(compiled['input_route'])
        self.assertTrue(all(r['prediction']['colors']==INITIAL and r['endpoint_audit']['full_route_replayed']
            for r in compiled['prefix_recoveries']))

    def test_selected_two_gesture_route_does_not_stop_at_original_target_intermediate(self):
        from native_live.same_session_dye_planner import _plan_fingerprint
        from native_live.candidate_selection import exact_observed_rules
        io=SyntheticTwoIO();events=[];chosen=[];labels=[];original_frames=io.frames
        route=[native_drag_gesture(io.geometry,io.settings,10,0).record()]*2
        def row(context,cp,rules,descriptors):
            pose=replay_native_route(cp['pose'],descriptors,io.geometry,io.settings,
                wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
            return audit_candidate_endpoint(context,cp,rules,dict(input_route=copy.deepcopy(descriptors),
                final_pose=pose,prediction=score_native_pose(io.session,pose,rules),needed=_needed(descriptors,3.,.5)))
        def planner(context,cp,frames,rules,grid,**kw):
            plan=plan_from_checkpoint(context,cp,frames,rules,grid,**kw)
            target=row(context,cp,rules,route);target['actual_colors']=MOVED
            plan['candidate_pool'].append(target);plan['plan_fingerprint']=_plan_fingerprint(plan)
            return plan
        def compiled(context,cp,rules,target,**kw):
            outward=row(context,cp,rules,route);returns=[]
            for index in (1,2):
                prefix=row(context,cp,rules,route[:index]);reference=dict(cp,pose=prefix['final_pose'],
                    client_hex=actual_colors(context,prefix['final_pose']))
                reverse=[native_drag_gesture(io.geometry,io.settings,-10*index,0).record()]
                returns.append(row(context,reference,exact_observed_rules(cp['client_hex']),reverse))
            outward.update(actual_colors=MOVED,selection_rules=exact_observed_rules(MOVED),
                prefix_recoveries=returns,protection_audit=dict(every_prefix_has_checked_return=True,prefix_count=2))
            return outward
        def frames(label,deadline):labels.append(label);return original_frames(label,deadline)
        io.frames=frames
        def choose(batch,deadline):
            if chosen:return None
            ready=[e for e in events if e['event']=='native_candidate_ready'][-1]
            chosen.append(True);return next(r['id'] for r in ready['candidates'] if r['colors']==MOVED)
        with patch('native_live.controller.compile_candidate_selection',side_effect=compiled):
            result=self.loop(io,rules_for(INITIAL),planner=planner,event=events.append,candidate_choice=choose)
        self.assertEqual(len(io.actions),2)
        self.assertEqual(result['actual_colors'],MOVED)
        self.assertFalse(result['accepted'])
        self.assertNotIn('selection_1_0_after',labels)
        self.assertIn('selection_1_1_after',labels)

    def test_failed_selection_return_never_marks_best_or_verified(self):
        io=SyntheticTwoIO();events=[];chosen=[];original=io.perform_candidate
        def drift(record,label,deadline):
            receipt=original(record,label,deadline)
            io.pose['position'][0]=.5
            return receipt
        io.perform_candidate=drift
        def choose(batch,deadline):
            if chosen:return None
            ready=[e for e in events if e['event']=='native_candidate_ready'][-1]
            chosen.append(True);return next(r['id'] for r in ready['candidates'] if not r['current'])
        with patch('native_live.controller.find_recovery',return_value=None):
            result=self.loop(io,rules_for(INITIAL),event=events.append,candidate_choice=choose)
        self.assertEqual(result['stop_reason'],'candidate_recovery_unconfirmed')
        self.assertFalse(result['verified'])
        self.assertFalse(result.get('best_current',False))
        self.assertEqual(len(io.actions),1)

    def test_selected_input_not_started_before_first_step_preserves_verified_anchor(self):
        io=SyntheticTwoIO();events=[];chosen=[];expired=[];original_check=io.check
        def check(deadline):
            if expired and deadline<80.:
                io.t=deadline+.001;expired.clear()
            original_check(deadline)
        io.check=check
        def event(row):
            events.append(row)
            if row['event']=='native_candidate_selected' and row['status']=='positioning':expired.append(True)
        def choose(batch,deadline):
            if chosen:return None
            ready=[e for e in events if e['event']=='native_candidate_ready'][-1]
            chosen.append(True);return next(r['id'] for r in ready['candidates'] if not r['current'])
        result=self.loop(io,rules_for(INITIAL),event=event,candidate_choice=choose)
        self.assertEqual(io.actions,[])
        self.assertEqual(result['actual_input_attempts'],0)
        self.assertNotEqual(result['stop_reason'],'internal_error')
        self.assertEqual(result['actual_colors'],INITIAL)

    def test_slower_selection_visual_updates_wait_close_reserve_for_fresh_final_read(self):
        io=SyntheticTwoIO();events=[];chosen=[];original=io.frames
        def frames(label,deadline):
            if label.startswith('selection_') and label.endswith('_after'):io.t+=6.
            if label=='candidate_wait_closed':io.t+=6.
            return original(label,deadline)
        io.frames=frames
        def choose(batch,deadline):
            if chosen:return None
            ready=[e for e in events if e['event']=='native_candidate_ready'][-1]
            row=next(r for r in ready['candidates'] if not r['current']);chosen.append(row['colors']);return row['id']
        result=self.loop(io,rules_for(INITIAL),event=events.append,candidate_choice=choose)
        self.assertEqual(result['actual_colors'],chosen[0],result.get('error'))
        self.assertTrue(result['verified'])
        self.assertTrue(any(o['label']=='candidate_wait_closed' for o in result['observations']))

    def test_candidate_collection_does_not_publish_an_audit_that_crossed_its_deadline(self):
        io=SyntheticTwoIO();context=io.context();cp=io.checkpoint('reference',100.);tick=[0.]
        row=dict(input_route=[],final_pose=cp['pose'],prediction=score_native_pose(io.session,cp['pose'],rules_for(INITIAL)),
            needed=_needed([],3.,.5))
        def check():tick[0]+=.1
        rows=collect_candidate_pool(context,cp,rules_for(INITIAL),[row]*30,
            deadline=.15,clock=lambda:tick[0],check=check)
        self.assertEqual(rows,[])
        self.assertLessEqual(tick[0],.2)


if __name__=='__main__':unittest.main()
