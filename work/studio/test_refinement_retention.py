"""Final polishing must not trade away a player's already measured colors."""
import copy
import itertools
from contextlib import contextmanager
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np


def black_rules():
    return [dict(enabled=True, exact=True, colors=['#000000'], tolerance=8., priority=i+1)
            for i in range(3)]


class RefinementPolicyTests(unittest.TestCase):
    def test_no_region_can_pay_for_another_regions_final_polish(self):
        from refinement_policy import compare_refinement
        rules = black_rules()
        similar = copy.deepcopy(rules); similar[0]['exact'] = False
        cases = (
            (['#020202','#505050','#808080'], ['#030303','#000000','#808080'], rules, False, [0]),
            (['#010101','#505050','#808080'], ['#181818','#000000','#808080'], similar, False, [0]),
            (['#171717','#010101','#020202'], ['#151515','#FFFFFF','#FFFFFF'], rules, False, [1,2]),
            (['#020202','#505050','#808080'], ['#020202','#000000','#808080'], rules, True, []),
            (['#020202','#505050','#808080'], ['#000000']*3, rules, True, []),
        )
        for before, after, active, want, regressions in cases:
            with self.subTest(before=before, after=after):
                decision = compare_refinement(after, before, active)
                self.assertEqual(decision['improved'], want)
                self.assertEqual(decision['regressed_regions'], regressions)

    def test_ties_missing_values_alternatives_and_disabled_regions(self):
        from refinement_policy import compare_refinement
        rules = black_rules(); rules[2]['enabled'] = False
        rules[0]['colors'].append('#FFFFFF')
        same = compare_refinement(['#FFFFFF','#020202',None], ['#000000','#020202',None], rules)
        self.assertTrue(same['not_worse']); self.assertFalse(same['improved'])
        lost = compare_refinement([None,'#000000',None], ['#000000','#020202',None], rules)
        self.assertFalse(lost['not_worse']); self.assertFalse(lost['verified'])
        hit = compare_refinement(['#FFFFFF','#000000',None], ['#000000','#020202',None], rules)
        self.assertTrue(hit['improved'])


class ScreenshotRetentionTests(unittest.TestCase):
    @contextmanager
    def controller(self, rules, colors):
        from screenshot_control import Controller, Budget
        with tempfile.TemporaryDirectory() as folder:
            owner = SimpleNamespace(folder=Path(folder),stop=threading.Event(),
                consume_retry_request=lambda:False,event=lambda *a,**kw:None)
            scene = SimpleNamespace(board=(0,0,360,320),markers=[(60,260),(180,120),(300,200)],cards=[])
            c = Controller(owner,None,scene,rules,Budget(120,.4))
            c.frame = np.zeros((320,360,3),np.uint8);c.check=lambda:None
            c.capture=lambda *a,**kw:c.frame;c.relocalize=lambda:True
            c.register=lambda *a:(np.eye(3),{})
            c.return_cost=lambda *a,**kw:0.;c.last_timer=time.monotonic();c.samples=object()
            c.move_to=lambda matrix,*a,**kw:(setattr(c,'pose',np.asarray(matrix).copy()) or True)
            with patch('screenshot_control.read_visible',side_effect=lambda *a,**kw:(next(colors),[])):
                c.observe('baseline')
                yield c
            c.close()

    def test_actual_trade_cannot_replace_best_or_escape_return(self):
        from screenshot_live import _refine, _publish
        for similar in (False,True):
            rules=black_rules();rules[0]['exact']=not similar
            baseline=['#010101' if similar else '#020202','#505050','#808080']
            trade=['#181818' if similar else '#030303','#000000','#808080']
            with self.subTest(similar=similar),self.controller(rules,iter([baseline,trade,baseline])) as c:
                desired=np.eye(3);desired[0,2]=.4
                with patch('screenshot_live.local_candidates',return_value=[dict(matrix=desired,kind='translate')]):
                    _refine(c,max_rounds=1)
                self.assertEqual(c.best['actual_colors'],baseline)
                self.assertEqual(c.current['actual_colors'],baseline)
                result=_publish(c)
                self.assertTrue(result['best_current'])

    def test_failed_return_does_not_certify_a_trade_as_best(self):
        from screenshot_live import _refine, _publish
        rules=black_rules();baseline=['#020202','#505050','#808080']
        trade=['#030303','#000000','#808080']
        with self.controller(rules,itertools.chain([baseline],itertools.repeat(trade))) as c:
            desired=np.eye(3);desired[0,2]=.4
            c.restore=lambda:c.current
            with patch('screenshot_live.local_candidates',return_value=[dict(matrix=desired,kind='translate')]):
                _refine(c,max_rounds=2)
            result=_publish(c)
            self.assertEqual(result['actual_colors'],trade)
            self.assertEqual(result['best_actual_colors'],baseline)
            self.assertFalse(result['best_current'])

    def test_successive_improvements_raise_the_floor(self):
        from screenshot_live import _refine
        baseline=['#020202','#505050','#808080']
        improved=['#020202','#404040','#808080']
        trade=['#020202','#484848','#000000']
        with self.controller(black_rules(),iter([baseline,improved,trade,improved])) as c:
            desired=np.eye(3);desired[0,2]=.4
            with patch('screenshot_live.local_candidates',return_value=[dict(matrix=desired,kind='translate')]):
                _refine(c,max_rounds=2)
            self.assertEqual(c.best['actual_colors'],improved)
            self.assertEqual(c.current['actual_colors'],improved)

    def test_actual_improvement_within_priority_bin_still_raises_floor(self):
        for similar,before,after in ((False,'#030303','#020202'),(True,'#171717','#010101')):
            rules=black_rules();rules[0]['exact']=not similar
            baseline=[before,'#505050','#808080'];improved=[after,'#505050','#808080']
            with self.subTest(similar=similar),self.controller(rules,iter([baseline,improved])) as c:
                c.refinement_anchor=c.best
                old_rank=c.best['rank']
                value=c.observe('refine-actual')
                self.assertEqual(value['rank'][:-2],old_rank[:-2])
                self.assertEqual(c.best['actual_colors'],improved)
                self.assertEqual(c.refinement_anchor['actual_colors'],improved)

    def test_local_pivot_follows_player_priority_before_matching_mode(self):
        from screenshot_refinement import local_candidates
        rules=black_rules();rules[0]['exact']=False
        markers=np.array([(60,260),(180,120),(300,200)])
        def field(points,indices):
            return np.zeros((*points.shape[:-1],3),np.uint8),np.ones(points.shape[:-1],bool),np.zeros(points.shape[:-1])
        rows=local_candidates(SimpleNamespace(visible_field=field),markers,rules,np.eye(3),limit=32)
        rotations=[r for r in rows if r['kind'] in ('rotate','scale')]
        self.assertTrue(rotations)
        for row in rotations:
            np.testing.assert_allclose(markers[0]@row['matrix'][:2,:2].T+row['matrix'][:2,2],markers[0],atol=1e-8)

    def test_global_search_still_allows_a_priority_ordered_trade(self):
        from screenshot_live import _search
        rules=black_rules();rules[0]['exact']=False
        baseline=['#010101','#505050','#808080'];trade=['#171717','#000000','#808080']
        with self.controller(rules,iter([baseline,trade])) as c:
            c.refinement_anchor=c.best
            c.restore=lambda:c.current
            samples=SimpleNamespace(period=100,arrays=lambda **kw:(
                [np.array([[0.,0.]])]*3,[np.zeros((1,3),np.uint8)]*3))
            desired=np.eye(3);desired[0,2]=5.
            with patch('screenshot_live.solve',return_value=dict(candidates=[dict(matrix=desired)])),patch('screenshot_live._refine'):
                _search(c,samples)
            self.assertEqual(c.best['actual_colors'],trade)

    def test_failed_polish_return_cannot_start_another_global_probe(self):
        from screenshot_live import _search, _refine
        baseline=['#020202','#505050','#808080'];trade=['#030303','#000000','#808080']
        with self.controller(black_rules(),itertools.chain([baseline,baseline],itertools.repeat(trade))) as c:
            main_moves=[];move=c.move_to
            def tracked(matrix,*a,**kw):
                if not a:main_moves.append(matrix)
                return move(matrix,*a,**kw)
            c.move_to=tracked;c.restore=lambda:c.current
            samples=SimpleNamespace(period=100,arrays=lambda **kw:(
                [np.array([[0.,0.]])]*3,[np.zeros((1,3),np.uint8)]*3))
            desired=np.eye(3);desired[0,2]=5.
            with patch('screenshot_live.solve',return_value=dict(candidates=[dict(matrix=desired)]*2)), \
                 patch('screenshot_live.local_candidates',return_value=[dict(matrix=desired,kind='translate')]), \
                 patch('screenshot_live._refine',side_effect=lambda c:_refine(c,max_rounds=1)):
                _search(c,samples)
            self.assertEqual(len(main_moves),1)

    def test_tolerance_loss_after_failed_return_does_not_bypass_retention(self):
        from screenshot_live import _search, _refine
        rules=black_rules()
        for rule in rules:rule['exact']=False
        baseline=['#010101','#505050','#808080'];trade=['#181818','#000000','#000000']
        with self.controller(rules,itertools.chain([baseline,baseline],itertools.repeat(trade))) as c:
            c.restore=lambda:c.current
            samples=SimpleNamespace(period=100,arrays=lambda **kw:(
                [np.array([[0.,0.]])]*3,[np.zeros((1,3),np.uint8)]*3))
            desired=np.eye(3);desired[0,2]=5.
            with patch('screenshot_live.solve',return_value=dict(candidates=[dict(matrix=desired)])), \
                 patch('screenshot_live.local_candidates',return_value=[dict(matrix=desired,kind='translate')]), \
                 patch('screenshot_live._refine',side_effect=lambda c:_refine(c,max_rounds=1)):
                _search(c,samples)
            self.assertNotIn('refinement-confirmation',[row['label'] for row in c.observations])
            self.assertFalse(c.at_least_best(c.current,c.best))

    def test_confirmation_regression_returns_to_refinement_floor(self):
        from screenshot_live import _search
        rules=black_rules()
        for rule in rules:rule['exact']=False
        baseline=['#010101','#505050','#808080'];improved=['#010101','#010101','#010101']
        trade=['#181818','#000000','#000000']
        with self.controller(rules,iter([baseline,baseline,improved,trade,improved])) as c:
            def refined(c):
                c.refinement_anchor=c.best
                c.observe('refine-actual')
            samples=SimpleNamespace(period=100,arrays=lambda **kw:(
                [np.array([[0.,0.]])]*3,[np.zeros((1,3),np.uint8)]*3))
            desired=np.eye(3);desired[0,2]=5.
            with patch('screenshot_live.solve',return_value=dict(candidates=[dict(matrix=desired)])), \
                 patch('screenshot_live._refine',side_effect=refined):
                _search(c,samples)
            self.assertEqual(c.current['actual_colors'],improved)
            self.assertTrue(c.at_least_best(c.current,c.best))

    def test_final_publish_confirmation_also_checks_retained_colors(self):
        from screenshot_live import _publish
        rules=black_rules()
        for rule in rules:rule['exact']=False
        baseline=['#010101']*3;trade=['#181818','#000000','#000000']
        with self.controller(rules,iter([baseline,trade,baseline,baseline])) as c:
            c.refinement_anchor=c.best
            result=_publish(c)
            self.assertTrue(result['accepted'])
            self.assertTrue(result['best_current'])
            self.assertEqual(result['actual_colors'],baseline)

    def test_visible_fallback_reads_each_trial_before_another_input(self):
        from screenshot_live import _refine
        baseline=['#020202','#505050','#808080']
        with self.controller(black_rules(),itertools.repeat(baseline)) as c:
            c.samples=None;seen=[]
            c.preview=lambda:dict(rank=c.current['rank'],matrix=c.pose.copy())
            c.fine_shift=lambda *a,**kw:seen.append(len(c.observations))
            c.rotate=lambda *a,**kw:None;c.wheel=lambda *a,**kw:None
            _refine(c)
            self.assertGreater(len(seen),1)
            self.assertGreater(seen[1],seen[0])

    def test_visible_fallback_probes_both_directions_from_retained_anchor(self):
        from screenshot_live import _refine
        baseline=['#020202','#505050','#808080']
        with self.controller(black_rules(),itertools.repeat(baseline)) as c:
            c.samples=None;angles=[];steps=[]
            c.fine_shift=lambda *a,**kw:None
            c.rotate=lambda angle,*a,**kw:angles.append(angle)
            c.wheel=lambda step,*a,**kw:steps.append(step)
            _refine(c)
            self.assertEqual(angles,[.35,-.35])
            self.assertEqual(steps,[1,-1])


class NativeRetentionTests(unittest.TestCase):
    # Reuse the saved-palette IO driver, real route compiler and controller.
    import test_native_refinement_controller as fixtures
    setUp=fixtures.ProtectedRefinementControllerTests.setUp
    candidate=fixtures.ProtectedRefinementControllerTests.candidate
    plan=fixtures.ProtectedRefinementControllerTests.plan
    refine=fixtures.ProtectedRefinementControllerTests.refine
    recover=fixtures.ProtectedRefinementControllerTests.recover
    run_loop=fixtures.ProtectedRefinementControllerTests.run_loop

    def test_measured_prefix_improvement_is_not_traded_by_remaining_polish(self):
        from native_input_compile import native_drag_gesture
        from refinement_policy import compare_refinement
        self.rules=black_rules();expected=[]
        def refine(context,cp,rules,**kw):
            self.refiner_calls+=1
            if self.refiner_calls>1:return None
            drag=native_drag_gesture(self.io.geometry,self.io.settings,2,0).record()
            row=self.candidate(context,cp,[drag,drag])
            returns=[]
            for length in (1,2):
                prefix=self.candidate(context,cp,[drag]*length)
                endpoint=dict(cp,pose=prefix['final_pose'],client_hex=prefix['prediction']['colors'])
                back=native_drag_gesture(self.io.geometry,self.io.settings,-2*length,0).record()
                returns.append(self.candidate(context,endpoint,[back]))
                if length==1:expected.extend(prefix['prediction']['colors'])
            self.assertTrue(compare_refinement(row['prediction']['colors'],cp['client_hex'],rules)['improved'])
            self.assertFalse(compare_refinement(row['prediction']['colors'],expected,rules)['not_worse'])
            row['prefix_recoveries']=returns
            return row
        result=self.run_loop(refine=refine)
        self.assertEqual(len(self.io.actions),1,result.get('error'))
        self.assertEqual(result['actual_colors'],expected)
        self.assertTrue(result['best_current'])

    def test_native_rejects_a_predicted_tolerance_trade_before_input(self):
        from native_input_compile import native_drag_gesture
        from native_input_response import replay_native_route
        from native_palette_scoring import score_native_pose
        from native_live.compromise import observed_quality
        route=[native_drag_gesture(self.io.geometry,self.io.settings,2,0).record()]
        pose=replay_native_route(self.io.pose,route,self.io.geometry,self.io.settings,
            wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
        neutral=black_rules();predicted=score_native_pose(self.io.session,pose,neutral)['colors']
        initial=list(self.io.cp['client_hex'])
        self.assertNotEqual(predicted[0],initial[0]);self.assertNotEqual(predicted[1],initial[1])
        self.rules=[dict(enabled=True,exact=i==1,colors=[initial[i] if i!=1 else predicted[i]],
            tolerance=8.,priority=i+1) for i in range(3)]
        self.assertGreater(observed_quality(predicted,self.rules),observed_quality(initial,self.rules))
        result=self.run_loop()
        self.assertEqual(self.io.actions,[])
        self.assertEqual(result['actual_colors'],initial,result.get('error'))

    def test_native_actual_tolerance_trade_returns_to_the_measured_anchor(self):
        from native_input_compile import native_drag_gesture
        from native_input_response import replay_native_route
        from native_palette_scoring import score_native_pose
        initial=list(self.io.cp['client_hex'])
        route=[native_drag_gesture(self.io.geometry,self.io.settings,2,0).record()]
        pose=replay_native_route(self.io.pose,route,self.io.geometry,self.io.settings,
            wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
        predicted=score_native_pose(self.io.session,pose,black_rules())['colors']
        self.rules=[dict(enabled=True,exact=i!=0,colors=[predicted[i] if i<2 else '#000000'],
            tolerance=40.,priority=i+1) for i in range(3)]
        disturbed=replay_native_route(self.io.pose,
            [native_drag_gesture(self.io.geometry,self.io.settings,3,-3).record()],
            self.io.geometry,self.io.settings,wheel_delta_per_step=1.,
            sample_policy='all_recorded_points')['final_pose']
        original=self.io.perform_candidate
        def actual(record,label,deadline):
            receipt=original(record,label,deadline)
            if len(self.io.actions)==1:self.io.pose=copy.deepcopy(disturbed)
            return receipt
        self.io.perform_candidate=actual
        from native_live.refinement import find_recovery
        result=self.run_loop(recover=find_recovery)
        self.assertGreaterEqual(len(self.io.actions),2,result.get('error'))
        self.assertEqual(result['refinement_attempts'][0]['status'],'restored')
        self.assertIn(0,result['refinement_attempts'][0]['comparison']['regressed_regions'])
        self.assertEqual(result['best_actual_colors'],initial)
        self.assertEqual(result['actual_colors'],initial)
        self.assertTrue(result['best_current'])

    def test_failure_return_planner_does_not_treat_a_trade_as_already_restored(self):
        from native_input_compile import native_drag_gesture
        from native_input_response import replay_native_route
        from native_palette_scoring import score_native_pose
        from native_live.retry_recovery import prepare_retry_recovery
        from native_live.same_session_dye_planner import bind_planning_context
        from refinement_policy import compare_refinement
        io=self.io
        def endpoint(dx,dy):
            pose=replay_native_route(io.pose,[native_drag_gesture(io.geometry,io.settings,dx,dy).record()],
                io.geometry,io.settings,wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
            return dict(copy.deepcopy(io.cp),pose=pose,
                client_hex=score_native_pose(io.session,pose,black_rules())['colors'])
        predicted=endpoint(2,0)['client_hex'];actual=endpoint(3,-3)
        rules=[dict(enabled=True,exact=i!=0,colors=[predicted[i] if i<2 else '#000000'],
            tolerance=40.,priority=i+1) for i in range(3)]
        context=bind_planning_context(io.session,io.cp,io.geometry,io.settings,wheel_delta_per_step=1.,
            calibration_evidence=dict(source='offline_test',viewport_origin=[0,0],viewport_scale=[1,1],
                backend_during_actions_synchronously_recorded=True))
        row=prepare_retry_recovery(context,actual,io.cp,rules,deadline=time.monotonic()+3.,preserve_regions=True)
        self.assertIsNotNone(row)
        self.assertTrue(row['input_route'])
        self.assertTrue(compare_refinement(row['prediction']['colors'],io.cp['client_hex'],rules)['not_worse'])


class RefinementPresentationTests(unittest.TestCase):
    def test_a_probe_is_distinguished_from_the_retained_result(self):
        from ui_progress import progress_text
        _,body=progress_text(dict(stage='refinement',refinement_status='trial',
            current_colors=['#030303','#000000'],current_deltas=[.82,0.],
            retained_colors=['#020202','#505050'],retained_deltas=[.55,33.89],
            verified=True,screenshot_verified=True))
        self.assertIn('试探',body)
        self.assertIn('已保留',body)
        self.assertIn('#030303',body);self.assertIn('#020202',body)

    def test_trial_and_retained_colors_remain_distinct_in_all_five_languages(self):
        import i18n
        from ui_progress import progress_text
        original=i18n.language
        try:
            _,body=progress_text(dict(stage='refinement',refinement_status='trial',
                current_colors=['#030303','#000000'],current_deltas=[.82,0.],
                retained_colors=['#020202','#505050'],retained_deltas=[.55,33.89],
                verified=True,screenshot_verified=True))
            for language,trial,retained in (
                    ('简体中文','当前试探','已保留配色'),('繁體中文','試探 · 遊戲實測','已保留配色'),
                    ('English','Trial colors','Retained colors'),('日本語','試行中の色','保持した配色'),
                    ('한국어','시험 중인 색상','보존한 배색')):
                with self.subTest(language=language):
                    i18n.set_language(language);text=str(i18n.tr(body))
                    self.assertIn(trial,text);self.assertIn(retained,text)
                    self.assertIn('#030303',text);self.assertIn('#020202',text)
                    self.assertIn('ΔE 0.82',text);self.assertNotIn('\\n',text)
        finally:i18n.set_language(original)

    def test_within_tolerance_does_not_hide_an_unconfirmed_return(self):
        from screenshot_presentation import result_text as screenshot_text
        from native_status import result_text as native_text
        from ui_progress import single_result_presentation
        data=dict(verified=True,accepted=True,best_current=False,
            outcome='matched',stop_reason='target_observed')
        for present in (screenshot_text,native_text,single_result_presentation):
            with self.subTest(presentation=present.__module__):
                _,body=present(data)
                self.assertIn('未回到',body)
                self.assertIn('游戏当前颜色',body)


if __name__=='__main__':unittest.main()
