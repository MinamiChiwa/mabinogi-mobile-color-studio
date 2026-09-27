import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from search_overlay import SearchOverlay
from atlas_service import AtlasService, AtlasCallbacks
from engine import Runner


class AtlasEndToEndTests(unittest.TestCase):
    def setUp(self):
        # These tests use an injected fake capture, not an installed OCR engine.
        configure=patch('engine.configure_ocr')
        configure.start()
        self.addCleanup(configure.stop)

    def test_runner_to_service_default_path(self):
        def acquire(owner,rules,**ctx):return 'capture'
        def build(capture,rules,**ctx):return {'quality_gate':{'passed':True},'candidates':[
            dict(id=0,dx=0,dy=0,accepted=True,maximum=0,average=0)],'board':(0,0,900,900),
            'batch_id':'batch-default','selection_deadline':time.monotonic()+30}
        def default(owner,report,candidate,rules,**ctx):
            return dict(candidate_id=candidate['id'],verified=True,accepted=True,
                        actual_pose=[[1,0,0],[0,1,0]])
        def choice(owner,report,candidate,rules,**ctx):raise AssertionError('choice should not run')
        service=AtlasService(AtlasCallbacks(acquire,build,default,choice,
                                            select=lambda *a,**k:None))
        events=[]
        with tempfile.TemporaryDirectory() as folder:
            runner=Runner(lambda kind,data:events.append((kind,data)),folder,atlas_runner=service.run)
            result=runner.launch([],strategy='atlas',mode='search')
        self.assertEqual(result['candidate_id'],0)
        self.assertEqual([kind for kind,_ in events],
                         ['config','atlas_status','atlas_ready','atlas_search_summary','atlas_candidates','atlas_default_verified',
                          'atlas_selection_expired','finished'])

    def test_overlay_click_reaches_runner_after_default_verification(self):
        def acquire(owner,rules,**ctx):return 'capture'
        rows=[dict(id=0,dx=0,dy=0,accepted=True,maximum=0,average=0),
              dict(id=4,dx=12,dy=12,accepted=True,maximum=1,average=1)]
        def build(capture,rules,**ctx):return {'quality_gate':{'passed':True},'candidates':rows,
                                              'board':(0,0,900,900),'batch_id':'batch-1',
                                              'selection_deadline':time.monotonic()+30}
        def default(owner,report,candidate,rules,**ctx):
            return dict(candidate_id=candidate['id'],verified=True,accepted=True,
                        actual_pose=[[1,0,0],[0,1,0]])
        def choice(owner,report,candidate,rules,**ctx):
            return dict(candidate_id=candidate['id'],verified=True,accepted=True,
                        actual_pose=[[1,0,candidate['dx']],[0,1,candidate['dy']]])
        service=AtlasService(AtlasCallbacks(acquire,build,default,choice))
        overlay=SimpleNamespace(batch_id=None,candidate_rows={},selection_sent=False,phase='choosing',
                                select_candidate=None)
        events=[]
        def emit(kind,data):
            events.append((kind,data))
            if kind=='atlas_candidates':
                overlay.phase='choosing'
                overlay.batch_id=data['batch_id']
                overlay.candidate_rows={row['id']:MagicMock() for row in data['candidates']}
            if kind=='atlas_default_verified':
                # This is the same callback used by the floating UI. Selection
                # becomes actionable only after the default has been verified.
                SearchOverlay.choose(overlay,overlay.batch_id,4)
        with tempfile.TemporaryDirectory() as folder:
            runner=Runner(emit,folder,atlas_runner=service.run)
            overlay.select_candidate=runner.choose_candidate
            result=runner.launch([],strategy='atlas')
        self.assertEqual(result['candidate_id'],4)
        self.assertTrue(overlay.selection_sent)
        self.assertEqual(overlay.candidate_rows[4].configure.call_args.args,())
        self.assertEqual(overlay.candidate_rows[4].configure.call_args.kwargs,{'state':'disabled'})
        kinds=[kind for kind,_ in events]
        self.assertLess(kinds.index('atlas_default_verified'),kinds.index('atlas_verified'))


if __name__=='__main__':unittest.main()
