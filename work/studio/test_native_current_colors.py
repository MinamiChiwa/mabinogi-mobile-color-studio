"""Live card labels follow every measured endpoint, without new OCR or success."""
import tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
import app
from native_live import service
from native_live.build_adapters import TW_ADAPTER
from native_live.controller import run_goal_loop
from test_native_planning_observation import PlanningReferenceIO
import test_native_ui_completion as completion

class CurrentColorsTests(unittest.TestCase):
    def test_every_completed_controller_readback_publishes_actual_colors(self):
        io=PlanningReferenceIO();events=[]
        with patch('native_live.controller.find_refinement',return_value=None):
            result=run_goal_loop(io,io.session,io.settings,io.case['rules'],engineering_deadline=100.,
                clock=io.clock,planner=io.plan,event=events.append)
        self.assertEqual(result['stop_reason'],'compromise_observed',result.get('error'))
        observations={r['label']:r for r in result['observations']}
        received={r['label']:r for r in events if r['event']=='native_observed'}
        self.assertEqual(set(received),set(observations))
        for label,row in observations.items():
            self.assertEqual(received[label]['colors'],row['checkpoint']['client_hex'])
        self.assertGreater(len(received),2)
        self.assertFalse(received['initial']['screenshot_verified'])
        final=next(reversed(received.values()))
        self.assertEqual(final['colors'],result['actual_colors'])
        self.assertTrue(final['screenshot_verified'])

    def test_service_delivers_each_readback_but_never_publishes_a_prediction_as_actual(self):
        rules=[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.)]*3
        streams=[['#123456','#654321','#0A0B0C'],['#ABCDEF','#FFFFFF','#010203'],['#FEDCBA','#111111','#222222']]
        events=[];target=__import__('window_target').WindowTarget(20,123,'Game','MabinogiMobile.exe')
        backend=MagicMock();backend.adapter=TW_ADAPTER
        def loop(*args,**kw):
            for index,colors in enumerate(streams):
                kw['event'](dict(event='native_observed',label='step-'+str(index),colors=colors,
                    screenshot_verified=index==2))
                kw['event'](dict(event='compromise_selected',prediction=dict(colors=['#000000']*3)))
            return dict(stop_reason='not_found_in_budget',actual_input_attempts=0,accepted=False,
                verified=False,actual_colors=[None]*3,actual_deltas=[None]*3)
        with tempfile.TemporaryDirectory() as folder:
            owner=SimpleNamespace(folder=Path(folder),stop=threading.Event(),event=lambda kind,**data:events.append((kind,data)))
            with patch.object(service,'resolve_target',return_value=target),patch.object(service,'_prepare',return_value=(backend,{})), \
                    patch.object(service,'collect_validation_session',return_value=dict(stop_reason='passive_baseline_collected',
                        capture=dict(capture_folder='unused'),baseline=dict(motion=dict(settings={})),session_deadline_monotonic=100.)), \
                    patch.object(service,'load_session',return_value=dict(pixels=[None]*3,picker_uv=[[1/6,.5],[.5,.5],[5/6,.5]])), \
                    patch.object(service,'InputSettings',return_value={}), \
                    patch.object(service,'ProjectClosedLoopIO',return_value=SimpleNamespace(input_attempts=0,release=lambda:None)), \
                    patch.object(service,'run_goal_loop',side_effect=loop):
                service.run_native_search(owner,rules,target=target)
        readbacks=[data for kind,data in events if kind=='native_colors']
        self.assertEqual([r['colors'] for r in readbacks],streams)
        self.assertEqual([r['screenshot_verified'] for r in readbacks],[False,False,True])
        self.assertTrue(all('accepted' not in r for r in readbacks))

    def test_main_cards_update_on_intermediate_and_full_reads_without_saving_success(self):
        ui=completion.NativeUICompletionTests().ui();ui.q.queue.clear()
        snapshots=[['#112233','#445566','#778899'],['#223344','#556677','#8899AA'],['#334455','#667788','#99AABB']]
        with patch.object(app,'save_result',side_effect=AssertionError('A live update is not a completed result')):
            for index,colors in enumerate(snapshots):
                ui.handle_event('native_colors',dict(colors=colors,screenshot_verified=index==2))
                actual=[card.current.configure.call_args.kwargs['text'] if card.current.configure.call_args else '' for card in ui.cards]
                self.assertTrue(all(color in label for color,label in zip(colors,actual)))
        self.assertTrue(ui.busy)
        self.assertEqual(ui.active_rules[0]['colors'],['#000000'])

    def test_two_region_updates_do_not_touch_unavailable_third_card(self):
        ui=completion.NativeUICompletionTests().ui();ui.q.queue.clear();ui.active_rules=ui.active_rules[:2]
        ui.cards[2].current.configure(text='当前颜色  本局不可用')
        for colors in (['#112233','#445566'],['#AABBCC','#DDEEFF']):
            ui.handle_event('native_colors',dict(colors=colors,screenshot_verified=False))
            for card,color in zip(ui.cards[:2],colors):
                self.assertIn(color,card.current.configure.call_args.kwargs['text'])
        self.assertEqual(ui.cards[2].current.configure.call_args.kwargs['text'],'当前颜色  本局不可用')

if __name__=='__main__':unittest.main()
