"""Independent affine game and clock: directional zoom is deliberately not reversible."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory

import numpy as np

from single_region_search import QuickSearchLimits,run_single_region
from single_region_live import SingleRegionIO


def scene():
    return SimpleNamespace(board=(0,0,300,300),
                           markers=[(50,150),(150,150),(250,150)],cards=[])


def rules(exact=True):
    return [dict(enabled=i==0,colors=['#000000'],exact=exact,
                 tolerance=8) for i in range(3)]


class StopRequested(Exception):pass


class AffineGame:
    def __init__(self,color=None,*,up=1.013,down=.991,native_limits=(.5,2),now=0.):
        self.now=float(now);self.pose=np.eye(3);self.up=up;self.down=down
        self.native_limits=native_limits;self.commands=[];self.events=[]
        self.frames={};self.reads=0;self.stopped=False
        self.color=color or (lambda game:'#111111')
        self.motion_available=True

    @property
    def scale(self):return float(np.sqrt(np.linalg.det(self.pose[:2,:2])))

    @property
    def source(self):return (np.linalg.inv(self.pose) @ [50,150,1])[:2]

    def clock(self):return self.now
    def check(self):
        if self.stopped:raise StopRequested('F9')
    def pause(self,seconds):self.check();self.now+=seconds
    def capture(self):
        self.check();self.now+=.025
        image=np.full((300,300,3),90,np.uint8)
        self.frames[id(image)]=self.pose.copy()
        return image
    def drag(self,board,dx,dy):
        self.check();self.commands.append(('drag',dx,dy,self.now));self.now+=.35
        matrix=np.eye(3);matrix[:2,2]=[dx,dy];self.pose=matrix@self.pose
    def wheel(self,board,steps,anchor=None):
        self.check();self.commands.append(('wheel',int(steps),tuple(anchor),self.now))
        self.now+=.15
        gain=(self.up**steps if steps>0 else self.down**(-steps))
        target=np.clip(self.scale*gain,*self.native_limits)
        gain=float(target/self.scale)
        pivot=np.asarray(anchor,float)
        matrix=np.eye(3);matrix[:2,:2]*=gain;matrix[:2,2]=pivot-gain*pivot
        self.pose=matrix@self.pose
    def measure(self,before,after,_scene):
        self.check();self.now+=.045
        if not self.motion_available:return None
        motion=self.frames[id(after)]@np.linalg.inv(self.frames[id(before)])
        return dict(matrix=motion.tolist(),origin=[0,0])
    def read(self,image,*,enabled,deadline):
        self.check();self.reads+=1;self.now+=.10
        return [self.color(self) if enabled[0] else None,None,None]
    def emit(self,kind,**data):self.events.append((kind,data))


class SingleZoomBehaviorTests(unittest.TestCase):
    def run_search(self,game,*,exact=True,limits=None,deadline=120,started=None):
        with patch('single_region_search.visible_candidates',return_value=[]):
            return run_single_region(game,scene(),rules(exact),game_deadline=deadline,
                search_started_at=started,limits=limits or QuickSearchLimits())

    def test_exact_match_exposed_by_zoom_finishes_without_a_followup_action(self):
        game=AffineGame(lambda g:'#000000' if g.scale<.98 or g.scale>1.025 else '#111111')
        result=self.run_search(game)
        self.assertTrue(result['accepted'])
        self.assertTrue(result['verified'])
        self.assertGreater(result['zoom_actions'],0)
        observations=[data for kind,data in game.events if kind=='single_observation']
        self.assertTrue(observations[-1]['accepted'])
        self.assertLess(game.now,30)

    def test_near_black_does_not_make_exact_mode_finish_under_the_old_move_limit(self):
        game=AffineGame(lambda g:'#010101')
        result=self.run_search(game)
        self.assertFalse(result['accepted'])
        self.assertTrue(result['verified'])
        self.assertGreater(game.now,55)
        self.assertLess(game.now,70)
        self.assertGreater(result['zoom_actions'],0)
        self.assertTrue(result['best_current'])

    def test_similar_mode_accepts_a_verified_near_black_without_waiting_sixty_seconds(self):
        game=AffineGame(lambda g:'#010101')
        result=self.run_search(game,exact=False)
        self.assertTrue(result['accepted'])
        self.assertLess(game.now,2)
        self.assertEqual(game.commands,[])

    def test_elapsed_search_budget_starts_at_the_board_not_at_launch_or_confirmation(self):
        game=AffineGame(now=49)
        result=self.run_search(game,deadline=120,started=0)
        self.assertLess(game.now,70)
        self.assertGreaterEqual(result['search_elapsed_seconds'],49)

    def test_return_uses_measured_sample_point_instead_of_reversing_the_wheel(self):
        game=AffineGame(lambda g:'#101010' if np.linalg.norm(g.source-[50,150])<1.1
                        else '#777777')
        result=self.run_search(game)
        self.assertTrue(result['best_current'])
        self.assertEqual(result['actual_colors'][0],'#101010')
        self.assertGreater(result['zoom_actions'],0)
        restore_at=next((i for i,(kind,data) in enumerate(game.events)
                         if kind=='single_progress' and data.get('stage')=='restore'),None)
        self.assertIsNotNone(restore_at)
        for kind,data in game.events[restore_at:]:
            if kind=='single_action' and data.get('restoring'):
                self.assertNotEqual(data.get('action'),'wheel')

    def test_native_zoom_limits_are_not_repeated_until_the_budget_expires(self):
        game=AffineGame(native_limits=(.99,1.02))
        result=self.run_search(game)
        self.assertTrue(result['verified'])
        wheel=[command for command in game.commands if command[0]=='wheel']
        self.assertGreater(len(wheel),0)
        self.assertLessEqual(len(wheel),16)
        self.assertTrue(all(abs(command[1])<=4 for command in wheel))
        self.assertGreaterEqual(result['relative_scale'],.99-1e-6)
        self.assertLessEqual(result['relative_scale'],1.02+1e-6)

    def test_unknown_direction_uses_one_notch_before_a_measured_burst(self):
        game=AffineGame()
        self.run_search(game)
        seen=set()
        for command in game.commands:
            if command[0]!='wheel':continue
            direction=int(np.sign(command[1]))
            if direction not in seen:self.assertEqual(abs(command[1]),1)
            seen.add(direction)
        self.assertTrue(seen)

    def test_failed_wheel_registration_retries_a_frame_without_reverse_input(self):
        game=AffineGame()
        original=game.measure
        fits=[]
        def measure(before,after,found_scene):
            fits.append(len([row for row in game.commands if row[0]=='wheel']))
            if fits[-1]:
                game.now+=.045
                return None
            return original(before,after,found_scene)
        game.measure=measure
        result=self.run_search(game)
        wheel=[row for row in game.commands if row[0]=='wheel']
        self.assertEqual(len(wheel),1)
        self.assertGreaterEqual(fits.count(1),2)
        self.assertTrue(result['verified'])
        self.assertFalse(result['restored'])

    def test_unmeasured_zoom_stops_before_stranding_verified_best(self):
        """A failed wheel fit must not start a new pose epoch and keep moving."""
        game=AffineGame(lambda g:'#000000' if g.scale < .98 else '#111111')
        original=game.measure
        wheel_measurements=0
        def measure(before,after,found_scene):
            nonlocal wheel_measurements
            if any(row[0]=='wheel' for row in game.commands):
                wheel_measurements += 1
                # Both the initial fit and its read-only retry fail.  The
                # physical wheel has happened, but its pose is unknown.
                if wheel_measurements >= 1:
                    game.now += .045
                    return None
            return original(before,after,found_scene)
        game.measure=measure
        result=self.run_search(game)
        wheel=[row for row in game.commands if row[0]=='wheel']
        self.assertEqual(len(wheel),1)
        self.assertEqual(result['reason'],'input_unverified')
        # No post-failure drag/zoom is allowed to strand the saved sample.
        wheel_index=next(i for i,row in enumerate(game.commands) if row[0]=='wheel')
        self.assertEqual(game.commands[wheel_index+1:],[])
        self.assertTrue(result['verified'])
        self.assertEqual(result['actual_colors'][0],'#111111')
        self.assertTrue(result['best_current'])

    def test_large_detents_do_not_oscillate_between_out_of_range_scales(self):
        game=AffineGame(up=2.,down=.5)
        result=self.run_search(game)
        wheel=[row for row in game.commands if row[0]=='wheel']
        self.assertLessEqual(len(wheel),4)
        self.assertAlmostEqual(result['relative_scale'],1.,places=6)
        self.assertGreater(game.now,54)

    def test_resampled_old_best_cannot_replace_the_better_current_scale_result(self):
        def color(game):
            if np.linalg.norm(game.source-[50,150])<1.1:
                return '#101010' if abs(game.scale-1.)<1e-6 else '#F0F0F0'
            return '#303030'
        game=AffineGame(color)
        result=self.run_search(game,limits=replace(QuickSearchLimits(),max_zoom_levels=2))
        self.assertEqual(result['best_actual_colors'][0],'#101010')
        self.assertFalse(result['best_current'])
        self.assertFalse(result['restored'])
        self.assertEqual(result['actual_colors'][0],'#303030')
        self.assertTrue(result['verified'])
        self.assertLess(game.now,70)

    def test_wheel_rgb_mismatch_keeps_geometry_only_for_recovery(self):
        owner = SimpleNamespace(event=lambda *args, **kwargs: None)
        game = SimpleNamespace(check=lambda: None)
        found = scene()
        def mismatch(before, after, scene, diagnostics, **kwargs):
            diagnostics.update(reason='material_rgb_mismatch',
                               attempts=[{'matrix': [[1, 0, 3], [0, 1, 4]]}])
            return None
        with TemporaryDirectory() as folder, \
                patch('single_region_live.motion', side_effect=mismatch), \
                patch('single_region_live.execution_diagnostics.submit'):
            io = SingleRegionIO(owner, game, found, folder, rules())
            io.motion_action = 'wheel'
            result = io.measure(np.zeros((8, 8, 3), np.uint8),
                                np.ones((8, 8, 3), np.uint8), found)
        self.assertTrue(result['geometry_only'])
        np.testing.assert_allclose(result['matrix'], [[1, 0, 3], [0, 1, 4]])

    def test_an_expensive_seed_does_not_hide_a_nearby_executable_exact_seed(self):
        game=AffineGame(lambda g:'#000000' if np.linalg.norm(g.source-[60,150])<.75
                        else '#111111',now=49.)
        rows=[dict(source=np.array([90.,290.]),screenshot_exact=True),
              dict(source=np.array([60.,150.]),screenshot_exact=True)]
        def proposals(_image,_scene,_rules,*,limit,excluded):
            return [row for row in rows if not any(
                np.linalg.norm(row['source']-point)<=4 for point in excluded)]
        with patch('single_region_search.visible_candidates',side_effect=proposals):
            result=run_single_region(game,scene(),rules(),game_deadline=120,
                                     search_started_at=0.)
        self.assertTrue(result['accepted'])
        self.assertEqual(result['actual_colors'][0],'#000000')
        self.assertEqual(game.commands[0][:3],('drag',-10,0))
        self.assertLess(game.now,60)

    def test_new_view_still_tries_exact_seeds_after_the_zoom_allowance_is_exhausted(self):
        target=np.array([10.,200.])
        game=AffineGame(lambda g:'#000000' if np.linalg.norm(g.source-target)<.75
                        else '#111111')
        def proposals(_image,_scene,_rules,*,limit,excluded):
            points=([target] if game.pose[0,2]>20 else
                    [np.array([40.,140.]),np.array([60.,140.])])
            rows=[]
            for point in points:
                source=(game.pose @ np.r_[point,1.])[:2]
                if not any(np.linalg.norm(source-p)<=4 for p in excluded):
                    rows.append(dict(source=source))
            return rows
        with patch('single_region_search.visible_candidates',side_effect=proposals):
            result=run_single_region(game,scene(),rules(),game_deadline=120,
                limits=replace(QuickSearchLimits(),max_zoom_levels=0,max_local_trials=0))
        self.assertTrue(result['accepted'])
        self.assertGreaterEqual(result['candidate_trials'],3)
        self.assertGreaterEqual(result['explorations'],1)
        self.assertEqual(result['zoom_actions'],0)

    def test_short_game_deadline_overrides_the_sixty_second_search_goal(self):
        game=AffineGame()
        result=self.run_search(game,deadline=15)
        self.assertLess(game.now,15)
        self.assertTrue(result['current'])
        self.assertTrue(result['verified'])
        self.assertFalse(result['accepted'])

    def test_f9_during_zoom_cannot_start_recovery_or_a_second_input(self):
        game=AffineGame()
        def wheel(*args,**kwargs):
            game.stopped=True
            raise StopRequested('F9')
        game.wheel=wheel
        with self.assertRaises(StopRequested):self.run_search(game)


if __name__=='__main__':unittest.main()
