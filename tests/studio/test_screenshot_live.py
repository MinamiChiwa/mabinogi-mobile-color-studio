"""Runner integration and fresh actual results on a saved synthetic board."""
import threading,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from engine import Runner

class ScreenshotLiveTests(unittest.TestCase):
    def test_stop_during_retry_wait_keeps_published_result_without_further_capture(self):
        from screenshot_live import run_screenshot_search
        from screenshot_control import Controller
        from vision import Scene
        scene=Scene(cards=[(0,0,10,10),(20,0,10,10)],markers=[(5,15),(25,20)],
            board=(0,10,30,40),colors=[None,None],seconds=120,button=None)
        captures=[];events=[]
        class Game:
            target=SimpleNamespace(title='fixture',hwnd=1,pid=2);hwnd=1
            def __init__(self,*a,**kw):pass
            def check(self):pass
            def release(self):pass
            def geometry(self):return (0,0,100,100)
            def capture(self):captures.append(1);return np.full((100,100,3),255,np.uint8)
            capture_waiting=capture
        with tempfile.TemporaryDirectory() as folder:
            def emit(kind,data):
                events.append((kind,data))
                if kind=='native_retry_available' and data.get('waiting_for_retry'):
                    owner.stop.request('overlay_stop_button');captures.clear()
            owner=Runner(emit,folder)
            rules=[dict(enabled=True,colors=['#000000'],exact=True,tolerance=0,priority=i+1) for i in range(2)]
            with patch('screenshot_live.recognize',return_value=scene),patch('screenshot_control.recognize',return_value=scene), \
                 patch('screenshot_control.read_visible',return_value=(['#222222','#333333'],[])), \
                 patch('screenshot_live.read_timer',return_value=120),patch('screenshot_control.read_timer',return_value=120), \
                 patch('screenshot_control.u.GetAsyncKeyState',return_value=0), \
                 patch('screenshot_live._collect',return_value=None),patch('screenshot_live._search'), \
                 patch.object(Controller,'restore') as restore:
                result=run_screenshot_search(owner,rules,game_factory=Game)
            self.assertEqual(captures,[]);self.assertEqual(restore.call_count,1)
            self.assertEqual(result['actual_colors'],['#222222','#333333'])
            self.assertTrue(result['verified']);self.assertTrue(result['measurement_retained'])
            self.assertEqual(result['stop_diagnostic']['source'],'overlay_stop_button')

    def processing_error_case(self,*,cancel=False,partial_input=False,fallback_stop=False,failure_kind=None):
        from screenshot_live import run_screenshot_search
        from screenshot_control import Controller
        from vision import Scene
        scene=Scene(cards=[(0,0,10,10),(20,0,10,10)],markers=[(5,15),(25,20)],
            board=(0,10,30,40),colors=[None,None],seconds=120,button=None)
        baseline=['#222222','#333333'];bad=['#DDDDDD','#EEEEEE'];moves=[]
        class Game:
            target=SimpleNamespace(title='fixture',hwnd=1,pid=2);hwnd=1
            def __init__(self,*args,**kwargs):self.colors=list(baseline)
            def check(self):pass
            def release(self):pass
            def geometry(self):return (0,0,100,100)
            def capture(self):return np.full((100,100,3),255,np.uint8)
            capture_waiting=capture
        def failed(c,*args):
            c.game.colors=list(bad);c.pose[0,2]=10.;c.current=None
            if cancel:c.owner.stop.set()
            if partial_input:
                def rejected():raise OSError('Fixture input completion unknown')
                c.act('input-failure',rejected)
            if failure_kind is not None:
                from platform_win import Interrupted
                if failure_kind is Interrupted:raise Interrupted('transient fixture interruption',reason='observation_unstable')
                raise failure_kind('transient fixture interruption',reason='layout_unreadable')
            raise ValueError('Fixture period processing error')
        def move(c,desired,*args,**kwargs):
            moves.append(np.asarray(desired).copy());c.pose=np.asarray(desired).copy()
            c.game.colors=list(baseline);c.actions.append(dict(name='return-fixture'));return True
        direct=np.eye(3);direct[0,2]=-10
        with tempfile.TemporaryDirectory() as folder:
            owner=Runner(lambda *args:None,folder)
            def registration(*args):
                if fallback_stop:
                    owner.stop.set();raise ValueError('Fixture recovery registration failed')
                return direct,{}
            rules=[dict(enabled=True,colors=['#000000'],exact=True,tolerance=8,priority=i+1) for i in range(2)]
            current=[None]
            def capture(owner,*args,**kwargs):current[0]=Game(owner);return current[0]
            with patch('screenshot_live.recognize',return_value=scene),patch('screenshot_control.recognize',return_value=scene), \
                 patch('screenshot_control.read_visible',side_effect=lambda *args,**kwargs:(list(current[0].colors),[])), \
                 patch('screenshot_live.read_timer',return_value=120),patch('screenshot_control.read_timer',return_value=120), \
                 patch('screenshot_control.u.GetAsyncKeyState',return_value=0), \
                 patch('screenshot_live._collect',side_effect=failed),patch.object(Controller,'register',side_effect=registration), \
                 patch.object(Controller,'move_to',new=move):
                result=run_screenshot_search(owner,rules,game_factory=capture,wait_for_retry=False)
        return result,moves

    def test_processing_error_restores_verified_best_before_reporting_compromise(self):
        result,moves=self.processing_error_case()
        self.assertEqual(len(moves),1)
        self.assertEqual(result['actual_colors'],['#222222','#333333'])
        self.assertTrue(result['best_current']);self.assertTrue(result['verified'])
        self.assertEqual(result['stop_reason'],'processing_error')

    def test_processing_error_never_restores_after_f9(self):
        result,moves=self.processing_error_case(cancel=True)
        self.assertEqual(moves,[])
        self.assertFalse(result['accepted'])

    def test_failed_gesture_can_restore_after_fresh_bound_image_registration(self):
        result,moves=self.processing_error_case(partial_input=True)
        self.assertEqual(len(moves),1)
        self.assertTrue(result['best_current'])

    def test_transient_palette_or_interruption_recovers_only_in_active_bound_game(self):
        from screenshot_control import PaletteEnded
        from platform_win import Interrupted
        for kind in (PaletteEnded,Interrupted):
            with self.subTest(kind=kind):
                try:result,moves=self.processing_error_case(failure_kind=kind)
                except Interrupted:self.fail('Recoverable interruption must publish the measured recovered result')
                self.assertEqual(len(moves),1)
                self.assertTrue(result['best_current'])

    def test_f9_during_failed_recovery_keeps_interruption_reason(self):
        result,moves=self.processing_error_case(fallback_stop=True)
        self.assertEqual(moves,[])
        self.assertEqual(result['stop_reason'],'interrupted')
        self.assertFalse(result['verified'])

    def test_fine_translation_drift_does_not_spend_best_return_time(self):
        from screenshot_live import _refine
        from screenshot_control import Controller,Budget
        from screenshot_search import actual_result
        with tempfile.TemporaryDirectory() as folder:
            rules=[dict(enabled=True,colors=['#FFFFFF'],exact=True,tolerance=8,priority=i+1) for i in range(3)]
            scene=SimpleNamespace(board=(0,0,701,701),markers=[(100,560),(350,200),(580,260)],cards=[])
            owner=SimpleNamespace(stop=threading.Event(),event=lambda *a,**k:None,folder=Path(folder))
            c=Controller(owner,None,scene,rules,Budget(12,.05))
            c.current=actual_result(['#AAAAAA','#BBBBBB','#CCCCCC'],rules)
            c.best=dict(c.current,matrix=np.eye(3))
            c.preview=lambda:dict(rank=c.current['rank'],matrix=c.pose.copy())
            shifts=[]
            def shift(*a,**k):shifts.append(a[0]);c.pose[:2]*=.9999
            c.fine_shift=shift;c.move_to=lambda *a,**k:True
            c.rotate=lambda *a,**k:None;c.observe=lambda *a:c.current;c.wheel=lambda *a:None
            _refine(c)
            self.assertEqual(len(shifts),2)
            self.assertTrue(c.budget.can_input(c.return_cost()))

    def test_short_search_skips_unrecoverable_zoom_and_tries_affordable_candidate(self):
        from screenshot_live import _search
        from screenshot_control import Controller,Budget
        from screenshot_samples import RawSamples
        from screenshot_search import actual_result
        with tempfile.TemporaryDirectory() as folder:
            rules=[dict(enabled=True,colors=['#FFFFFF'],exact=True,tolerance=8,priority=i+1) for i in range(2)]
            scene=SimpleNamespace(board=(0,0,300,300),markers=[(75,150),(225,150)],cards=[])
            owner=SimpleNamespace(stop=threading.Event(),event=lambda *a,**k:None,
                consume_retry_request=lambda:False,folder=Path(folder))
            c=Controller(owner,None,scene,rules,Budget(12,.05))
            c.current=actual_result(['#AAAAAA','#BBBBBB'],rules)
            c.best=dict(c.current,matrix=np.eye(3));c.check=lambda:None
            samples=RawSamples(150,rules)
            moved=[]
            def move(matrix):moved.append(matrix);c.pose=matrix.copy();return True
            c.move_to=move;c.observe=lambda *a:c.current;c.restore=lambda:None
            affordable=np.eye(3);affordable[0,2]=8
            candidates=[dict(matrix=np.diag([1.01,1.01,1.])),dict(matrix=affordable)]
            with patch('screenshot_live.solve',return_value=dict(candidates=candidates)),patch('screenshot_live._refine'):
                self.assertIs(_search(c,samples),samples)
            self.assertEqual(len(moved),1)
            np.testing.assert_array_equal(moved[0],affordable)

    def test_short_refinement_does_not_zoom_away_from_an_affordable_best(self):
        from screenshot_live import _refine
        from screenshot_control import Controller,Budget
        from screenshot_search import actual_result
        for known in (True,False):
            with self.subTest(known=known),tempfile.TemporaryDirectory() as folder:
                rules=[dict(enabled=True,colors=['#FFFFFF'],exact=True,tolerance=8,priority=i+1) for i in range(2)]
                scene=SimpleNamespace(board=(0,0,300,300),markers=[(75,150),(225,150)],cards=[])
                owner=SimpleNamespace(stop=threading.Event(),event=lambda *a,**k:None,folder=Path(folder))
                c=Controller(owner,None,scene,rules,Budget(12,.05));c.pose_known=known
                c.current=actual_result(['#AAAAAA','#BBBBBB'],rules)
                c.best=dict(c.current,matrix=np.eye(3))
                c.preview=lambda:dict(rank=c.current['rank'],matrix=np.eye(3))
                c.fine_shift=lambda *a,**k:None;c.move_to=lambda *a,**k:True
                c.rotate=lambda *a,**k:None;c.observe=lambda *a:c.current
                zooms=[]
                def wheel(steps,*a):
                    zooms.append(steps);c.pose[:2]*=1.01**steps if steps>0 else .99**-steps
                c.wheel=wheel
                _refine(c)
                self.assertEqual(zooms,[])

    def test_failed_zoom_registration_uses_cached_search_without_further_zoom(self):
        from screenshot_live import _collect
        from screenshot_control import Controller,Budget
        from screenshot_samples import RawSamples
        with tempfile.TemporaryDirectory() as folder:
            rules=[dict(enabled=True,colors=['#FFFFFF'],exact=True,tolerance=8,priority=i+1) for i in range(2)]
            scene=SimpleNamespace(board=(0,0,300,300),markers=[(75,150),(225,150)],cards=[])
            owner=SimpleNamespace(stop=threading.Event(),event=lambda *a,**k:None,
                consume_retry_request=lambda:False,folder=Path(folder))
            c=Controller(owner,None,scene,rules,Budget(25,.1))
            c.frame=np.zeros((300,300,3),np.uint8)
            c.best=dict(matrix=np.eye(3),frame=c.frame,verified=True,rank=(1,0))
            c.check=lambda:None;c.relocalize=lambda:False
            zooms=[]
            def wheel(steps,label):
                zooms.append(steps);c.pose_known=False
                c.budget.deadline-=abs(steps)*.045+.7
            c.wheel=wheel
            samples=RawSamples(150,rules);samples.frames=6
            self.assertIs(_collect(c,samples),samples)
            self.assertEqual(zooms,[-25])

    def test_short_entry_and_retry_keep_best_reachable_while_search_remains_available(self):
        from screenshot_live import _collect
        from screenshot_control import Controller,Budget
        from screenshot_samples import RawSamples
        for cached in (False,True):
            with self.subTest(cached=cached),tempfile.TemporaryDirectory() as folder:
                rules=[dict(enabled=True,colors=['#FFFFFF'],exact=True,tolerance=8,priority=i+1) for i in range(2)]
                scene=SimpleNamespace(board=(0,0,300,300),markers=[(75,150),(225,150)],cards=[])
                owner=SimpleNamespace(stop=threading.Event(),event=lambda *a,**k:None,
                    consume_retry_request=lambda:False,folder=Path(folder))
                c=Controller(owner,None,scene,rules,Budget(10,.04))
                c.frame=np.zeros((300,300,3),np.uint8)
                c.best=dict(matrix=np.eye(3),frame=c.frame,verified=True,rank=(1,0))
                c.check=lambda:None
                zooms=[]
                def wheel(steps,label):
                    zooms.append(steps);c.pose[:2]*=.99**abs(steps)
                    c.budget.deadline-=abs(steps)*.045+.7
                c.wheel=wheel
                samples=RawSamples(150,rules) if cached else None
                if samples is not None:samples.frames=6
                result=_collect(c,samples)
                self.assertTrue(c.budget.can_input(c.return_cost()))
                self.assertEqual(len(zooms),0)
                self.assertIs(result,samples)

    def test_retry_at_measured_minimum_does_not_repeat_redundant_zoom_batches(self):
        from screenshot_live import _collect
        from screenshot_samples import RawSamples
        from screenshot_control import Budget
        scene=SimpleNamespace(board=(0,0,300,300),markers=[(75,150),(225,150)],cards=[])
        rules=[dict(enabled=True,colors=['#FFFFFF'],exact=True,tolerance=8,priority=i+1) for i in range(2)]
        samples=RawSamples(150,rules);samples.frames=6
        zooms=[]
        c=SimpleNamespace(scene=scene,rules=rules,pose=np.eye(3),pose_known=True,budget=Budget(120,.4),
            frame=np.zeros((300,300,3),np.uint8),progress=lambda *a,**k:None,
            check=lambda:None,owner=SimpleNamespace(consume_retry_request=lambda:False),
            return_cost=lambda **kw:0.,
            wheel=lambda steps,label:zooms.append(steps),relocalize=lambda:True)
        result=_collect(c,samples)
        self.assertIs(result,samples)
        self.assertEqual(len(zooms),1)
        self.assertGreater(samples.frames,6)

    def test_retry_during_time_return_keeps_session_alive(self):
        from screenshot_live import run_screenshot_search
        from screenshot_control import TimeEnded,RetryRequested
        from vision import Scene
        scene=Scene(cards=[(0,0,10,10),(20,0,10,10)],markers=[(5,15),(25,20)],
            board=(0,10,30,40),colors=[None,None],seconds=80,button=None)
        class Game:
            target=SimpleNamespace(title='game',hwnd=1,pid=2);hwnd=1
            def __init__(self,*a,**kw):pass
            def check(self):pass
            def release(self):pass
            def geometry(self):return (0,0,100,100)
            def capture(self):return np.full((100,100,3),255,np.uint8)
            capture_waiting=capture
        with tempfile.TemporaryDirectory() as folder:
            owner=Runner(lambda *a:None,folder)
            rules=[dict(enabled=True,colors=['#112233'],exact=True,tolerance=8,priority=i+1) for i in range(3)]
            with patch('screenshot_live.recognize',return_value=scene),patch('screenshot_control.recognize',return_value=scene), \
                 patch('screenshot_control.read_visible',return_value=(['#556677','#556677'],[])), \
                 patch('screenshot_live.read_timer',return_value=80),patch('screenshot_control.read_timer',return_value=80), \
                 patch('screenshot_control.u.GetAsyncKeyState',return_value=0), \
                 patch('screenshot_live._collect',side_effect=[TimeEnded(),None]) as collect, \
                 patch('screenshot_live._search',return_value=None), \
                 patch('screenshot_control.Controller.restore',side_effect=[RetryRequested(),None]):
                result=run_screenshot_search(owner,rules,game_factory=Game,wait_for_retry=False)
            self.assertNotEqual(result['stop_reason'],'processing_error')
            self.assertEqual(collect.call_count,2)

    def test_visual_factory_and_single_rule_use_replacement_service(self):
        import app
        with tempfile.TemporaryDirectory() as folder:
            runner=app.build_runner(lambda *a:None,folder,'atlas')
            self.assertTrue(callable(getattr(runner,'screenshot_runner',None)))
            self.assertIsNone(runner.atlas_runner)

    def test_replacement_runs_for_single_region_and_finishes_cleanup(self):
        events=[]
        with tempfile.TemporaryDirectory() as folder:
            def visual(owner,rules,**kw):
                return {'accepted':False,'rules':rules}
            runner=Runner(lambda k,d:events.append((k,d)),folder,screenshot_runner=visual)
            rules=[dict(enabled=i==0,colors=['#000000'],exact=True,tolerance=8) for i in range(3)]
            with patch('engine.configure_ocr'),patch('engine.start_session_cleanup'):
                result=runner.launch(rules,strategy='atlas')
            self.assertFalse(result['accepted']);self.assertEqual(result['rules'],rules)
            self.assertEqual(events[-1][0],'finished')
            self.assertEqual(events[0][1]['strategy'],'screenshot')

    def test_already_matching_board_is_double_read_with_zero_input(self):
        from screenshot_live import run_screenshot_search
        from vision import Scene
        scene=Scene(cards=[(0,0,10,10),(20,0,10,10)],markers=[(5,15),(25,20)],
            board=(0,10,30,40),colors=[None,None],seconds=80,button=None)
        class Game:
            target=SimpleNamespace(title='game',hwnd=1,pid=2)
            hwnd=1
            def __init__(self,*a,**kw):self.stop=a[0];self.inputs=[]
            def check(self):pass
            def release(self):pass
            def geometry(self):return (0,0,100,100)
            def capture(self):return np.full((100,100,3),255,np.uint8)
            capture_waiting=capture
        events=[]
        with tempfile.TemporaryDirectory() as folder:
            owner=Runner(lambda k,d:events.append((k,d)),folder)
            rules=[dict(enabled=True,colors=['#112233'],exact=True,tolerance=8,priority=i+1) for i in range(3)]
            with patch('screenshot_live.recognize',return_value=scene),patch('screenshot_control.recognize',return_value=scene), \
                 patch('screenshot_control.read_visible',return_value=(['#112233','#112233'],[])), \
                 patch('screenshot_live.read_timer',return_value=80), \
                 patch('screenshot_control.read_timer',return_value=80), \
                 patch('screenshot_control.u.GetAsyncKeyState',return_value=0):
                result=run_screenshot_search(owner,rules,game_factory=Game,wait_for_retry=False)
            self.assertTrue(result['accepted']);self.assertTrue(result['verified'])
            self.assertEqual(result['region_count'],2)
            data=__import__('json').loads((Path(folder)/'screenshot/result.json').read_text())
            self.assertEqual(data['actions'],0);self.assertGreaterEqual(data['actual_reads'],2)

if __name__=='__main__':unittest.main()
