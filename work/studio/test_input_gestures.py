import json
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch
import numpy as np

from input_gestures import drag_gesture, rotation_gesture, wheel_gesture
from atlas_execution import reposition_budget


class GestureGeometryTests(unittest.TestCase):
    def test_physical_integer_paths_stay_inside_different_boards(self):
        for board in ((714,425,1212,923),(1125,258,1826,959),(-800,-500,400,700)):
            l,t,r,b=board
            for anchor in (((l+r)/2,(t+b)/2),(l+(r-l)*.12,b-(b-t)*.12)):
                for angle in (-180,-12,-.4,.01,.4,12,180):
                    gesture=rotation_gesture(board,angle,anchor)
                    self.assertTrue(all(type(v) is int for p in gesture.points for v in p))
                    self.assertTrue(all(l<x<r and t<y<b for x,y in gesture.points))
                    self.assertEqual(gesture.anchor,tuple(map(round,anchor)))

    def test_noop_arc_is_distinct_from_radial_motion(self):
        gesture=rotation_gesture((714,425,1212,923),.01,(963,674))
        self.assertGreater(len(set(gesture.points)),1)
        self.assertEqual(len(set(gesture.points[gesture.arc_start:])),1)
        self.assertFalse(gesture.has_effect)
        self.assertEqual(gesture.duration,0)

    def test_integer_cursor_arc_is_not_reported_as_calibration(self):
        gesture=rotation_gesture((714,425,1212,923),.1,(963,674))
        self.assertTrue(gesture.has_effect)
        self.assertNotAlmostEqual(gesture.arc_degrees,gesture.requested_angle,places=3)
        self.assertEqual(gesture.record()['response_model'],'unverified_cursor_geometry')
        json.dumps(gesture.record(),allow_nan=False)

    def test_drag_descriptor_reports_actual_clipped_translation(self):
        gesture=drag_gesture((0,0,300,300),999,-1.9)
        self.assertEqual(gesture.translation,(195,-1))
        self.assertEqual(gesture.points[0],(52,150))
        self.assertEqual(len(gesture.points),25)

    def test_wheel_uses_whole_notches_and_rounded_anchor(self):
        gesture=wheel_gesture((0,0,300,300),-4,(60.8,91.3))
        self.assertEqual(gesture.anchor,(61,91))
        self.assertEqual(gesture.wheel_steps,-4)
        for steps in (.5,float('nan'),float('inf')):
            with self.assertRaises(ValueError):wheel_gesture((0,0,300,300),steps)
        with self.assertRaises(ValueError):wheel_gesture((0,0,300,300),1,(.1,60))

    def test_cached_plan_cannot_be_modified(self):
        first=rotation_gesture((0,0,498,498),12,(249,249))
        self.assertIs(first,rotation_gesture((0,0,498,498),12,(249,249)))
        with self.assertRaises(FrozenInstanceError):first.requested_angle=20

    def test_budget_contains_integer_inputs_and_explicit_model_limit(self):
        row=dict(dx=45,dy=-20,angle=24,scale=1.01**-4)
        plan=reposition_budget(row,0,100,(0,0,498,498),markers=((83,200),(249,350),(415,220)))
        self.assertTrue(plan['allowed'])
        self.assertEqual(len(plan['input_route']),sum(plan['actions'].values()))
        self.assertEqual(plan['response_model'],'grouped_integer_arc_and_directional_zoom')
        self.assertFalse(plan['game_response_verified'])
        for gesture in plan['input_route']:
            self.assertTrue(gesture['has_effect'])
            self.assertTrue(all(type(v) is int for p in gesture['points'] for v in p))


class GestureInputTests(unittest.TestCase):
    def test_opt_in_cursor_trace_records_actual_client_coordinates(self):
        game=self.game();game.capture_input_trace=True
        game.geometry=lambda:(-100,50,1280,960)
        gesture=rotation_gesture((100,100,600,600),.4)
        def cursor(pointer):
            point=game.moves[-1]
            pointer._obj.x=point[0]-100;pointer._obj.y=point[1]+50
            return 1
        with patch('platform_win.time.sleep'),patch('platform_win.u.GetCursorPos',side_effect=cursor):
            game.perform_gesture(gesture)
        self.assertEqual(len(game.last_input_trace),len(gesture.points))
        self.assertEqual([r['actual_client'] for r in game.last_input_trace],list(map(list,gesture.points)))
        self.assertEqual(game.events,[((8,),{}),((16,),{})])

    def test_cursor_trace_failure_cannot_interrupt_input_or_release(self):
        game=self.game();game.capture_input_trace=True
        game.geometry=lambda:(0,0,1280,960)
        with patch('platform_win.time.sleep'),patch('platform_win.u.GetCursorPos',return_value=0):
            game.perform_gesture(rotation_gesture((100,100,600,600),.4))
        self.assertTrue(all(r['actual_client'] is None for r in game.last_input_trace))
        self.assertEqual(game.events,[((8,),{}),((16,),{})])

    def game(self):
        from platform_win import Game
        game=Game.__new__(Game)
        game.check=lambda:None
        game.moves=[];game.events=[]
        game.move_to=game.moves.append
        game.send=lambda *args,**kw:game.events.append((args,kw))
        return game

    def test_exact_descriptor_is_sent_with_duplicate_waits_preserved(self):
        game=self.game()
        gesture=rotation_gesture((0,0,498,498),.1,(249,249))
        with patch('platform_win.time.sleep') as sleep:
            game.perform_gesture(gesture)
        expected=[gesture.points[0]]+[p for p,prev in zip(gesture.points[1:],gesture.points) if p!=prev]
        self.assertEqual(game.moves,expected)
        self.assertIs(game.last_gesture,gesture)
        self.assertEqual(game.events,[((8,),{}),((16,),{})])
        self.assertEqual(sleep.call_count,3+len(gesture.points)-1)
        self.assertAlmostEqual(sum(c.args[0] for c in sleep.call_args_list),gesture.duration)

    def test_zero_arc_never_sends_even_radial_input(self):
        game=self.game()
        with patch('platform_win.time.sleep') as sleep:
            self.assertFalse(game.perform_gesture(rotation_gesture((0,0,498,498),.01,(249,249))))
        self.assertEqual(game.moves,[]);self.assertEqual(game.events,[])
        sleep.assert_not_called()

    def test_button_release_is_attempted_after_down_failure(self):
        game=self.game()
        def send(flags):
            game.events.append(flags)
            if flags==8:raise RuntimeError('input rejected')
        game.send=send
        with patch('platform_win.time.sleep'):
            with self.assertRaisesRegex(RuntimeError,'input rejected'):
                game.perform_gesture(rotation_gesture((0,0,498,498),12,(249,249)))
        self.assertEqual(game.events,[8,16])

    def test_runtime_adapter_does_not_regenerate_the_planned_input(self):
        from atlas_runtime import Adapter
        from types import SimpleNamespace
        game=self.game();game.initial=(0,0,1280,960)
        adapter=Adapter(game,SimpleNamespace(board=(0,0,498,498)), 'test')
        gesture=wheel_gesture((0,0,498,498),-4,(123,234))
        with patch('platform_win.time.sleep'):
            adapter.perform_gesture(gesture)
        self.assertIs(game.last_gesture,gesture)
        self.assertEqual(game.events,[((0x800,),{'data':-120})]*4)
        self.assertEqual(game.moves[0],gesture.anchor)

    def test_quantized_response_uses_actual_measurement_and_logs_same_input(self):
        from test_atlas_similarity_execution import SimilarityGame
        from atlas_execution import CandidateBatch, execute_candidate
        game=SimilarityGame();seen=[]
        def perform(gesture):
            seen.append(gesture.record())
            if gesture.kind=='rotate':
                game.gesture('rotate',gesture.arc_degrees*.99,1,gesture.anchor)
            elif gesture.kind=='wheel':
                game.wheel(gesture.wheel_steps,gesture.anchor)
            else:game.drag(*gesture.translation)
        game.perform_gesture=perform
        row=dict(id=0,dx=85,dy=-45,angle=24,scale=1.01**-4,colors=['#112233']*3,deltas=[0]*3)
        rules=[dict(enabled=True,exact=False,tolerance=8,colors=['#112233'])]*3
        batch=CandidateBatch([row],game.ctx,1000,clock=lambda:0)
        events=[]
        result=execute_candidate(game,batch,batch.id,0,game.capture(),rules,
                                 emit=lambda kind,data:events.append((kind,data)),clock=lambda:0)
        self.assertLessEqual(max(result['marker_errors']),1)
        self.assertEqual(seen,[v['gesture'] for k,v in events if k=='atlas_command'])
        self.assertEqual(seen,[v['gesture'] for k,v in events if k=='atlas_positioning'])
        np.testing.assert_allclose(result['actual_pose'],game.pose[:2])


if __name__=='__main__':unittest.main()
