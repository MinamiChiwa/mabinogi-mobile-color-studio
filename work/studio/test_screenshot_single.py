"""Fast single-region screenshot search contracts."""
import tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np

def single_rules():
    return [dict(enabled=i==0,colors=['#000000'],exact=True,tolerance=8.,priority=i+1)
            for i in range(3)]

class ScreenshotSingleRegionTests(unittest.TestCase):
    def test_exploration_match_under_marker_is_verified_before_further_input(self):
        from screenshot_live import _collect,_search
        from screenshot_search import actual_result
        c=self.controller(np.full((160,100,3),220,np.uint8))
        c.scene.board=(0,60,100,160);c.scene.markers=[(25,110),(50,110),(75,110)]
        c.scene.cards=[(0,0,25,40),(35,0,25,40),(70,0,25,40)]
        wheels=[];reads=[]
        def wheel(steps,label):
            wheels.append(steps)
            if len(wheels)>1:self.fail('An already matched marker was moved again')
            c.pose[:2,:2]*=.99**25
            c.frame[12:23,7:18]=0  # Active card swatch; target is hidden under the marker.
            c.current=None
        def read(label,**kw):
            reads.append(label);c.current=actual_result(['#000000',None,None],c.rules)
            return c.current
        c.wheel=wheel;c.observe=read
        c.move_to=lambda *a,**kw:self.fail('An already matched marker needs no positioning')
        c.restore=lambda:c.current
        _collect(c,None);_search(c,None)
        self.assertEqual(wheels,[-25])
        self.assertEqual(reads,['single-visible-actual','single-match-confirmation'])
        self.assertTrue(c.current['accepted'])

    def test_relocalized_rotation_allows_a_new_approach_to_the_same_source(self):
        from screenshot_single import candidates
        c=self.controller(np.full((100,100,3),220,np.uint8));c.frame[50,20]=0
        row=candidates(c)[0];c.single_seen={row['signature']}
        angle=np.radians(4);linear=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
        c.pose[:2,:2]=linear;c.pose[:2,2]=row['point']-linear@row['source']
        self.assertTrue(candidates(c),'A changed rotation must not inherit a failed approach signature')

    def test_single_verification_skips_disabled_card_timeout_and_keeps_region_index(self):
        for active in range(3):
            with self.subTest(region=active):
                c=self.controller(np.zeros((100,300,3),np.uint8))
                c.rules=single_rules()
                for i,rule in enumerate(c.rules):rule['enabled']=i==active
                c.scene.cards=[(i*100,0,100,100) for i in range(3)]
                c.last_timer=time.monotonic()
                def font_read(image,card,**kw):
                    if card!=c.scene.cards[active]:raise TimeoutError('disabled card')
                    return dict(hex='#000000',threshold_reads=[dict(text='#000000')]*2)
                with patch('native_live.game_font_reader.read_hex',side_effect=font_read):
                    result=c.observe('single-actual',reuse_frame=True)
                self.assertTrue(result['accepted'])
                self.assertEqual(result['actual_colors'],['#000000' if i==active else None for i in range(3)])
                self.assertEqual(result['text'][0]['region'],active)

    def test_failed_visible_targets_do_not_reset_shrinking_progress_to_best_scale(self):
        from screenshot_live import _collect,_search
        from screenshot_search import actual_result
        c=self.controller(np.full((100,100,3),220,np.uint8));c.frame[50,20]=0
        c.best=dict(actual_result(['#CCCCCC',None,None],c.rules),matrix=np.eye(3),frame=c.frame.copy())
        c.current=c.best;scales=[];restores=[]
        def wheel(steps,label):
            if steps>0:c.pose[:2,:2]*=1.01**steps;return
            if len(scales)>=8:self.fail('Failed targets repeated the shrink chain')
            current=np.hypot(c.pose[0,0],c.pose[1,0]);factor=max(.99**100,current*.99**25)/current
            c.pose[:2,:2]*=factor;scales.append(float(np.hypot(c.pose[0,0],c.pose[1,0])))
        def move(matrix,*a,**kw):c.pose=matrix.copy();return True
        def read(*a,**kw):
            c.current=actual_result(['#EEEEEE',None,None],c.rules);return c.current
        def restore():
            restores.append(True);c.pose=np.eye(3);c.current=c.best;return c.current
        c.wheel=wheel;c.move_to=move;c.observe=read;c.restore=restore
        c.drag=lambda *a,**kw:None
        _collect(c,None);_search(c,None)
        self.assertEqual(len(scales),5)
        self.assertTrue(all(a>b for a,b in zip(scales,scales[1:4])))
        self.assertEqual(len(restores),1)

    def test_relocalized_pose_rebuilds_cached_visible_candidate(self):
        from screenshot_live import _collect,_search
        from screenshot_search import actual_result
        c=self.controller(np.full((100,100,3),220,np.uint8));c.frame[50,20]=0
        _collect(c,None);c.pose_known=False
        def relocalize():c.pose=np.eye(3);c.pose[0,2]=10;c.pose_known=True;return True
        c.relocalize=relocalize;moved=[]
        c.move_to=lambda matrix,*a,**kw:moved.append(matrix.copy()) or True
        c.observe=lambda *a,**kw:actual_result(['#000000',None,None],single_rules())
        c.restore=lambda:None
        _search(c,None)
        self.assertEqual(moved[0][0,2],15.)
    def controller(self,frame):
        from screenshot_control import Controller,Budget
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        owner=SimpleNamespace(stop=threading.Event(),consume_retry_request=lambda:False,
            event=lambda *a,**kw:None,folder=Path(folder.name))
        scene=SimpleNamespace(board=(0,0,100,100),markers=[(25,50),(50,50),(75,50)],cards=[])
        c=Controller(owner,None,scene,single_rules(),Budget(120,.4));c.check=lambda:None
        c.frame=frame;c.reference=frame.copy();return c

    def test_visible_target_skips_period_sampling_and_full_palette_scan(self):
        from screenshot_live import _collect
        frame=np.full((100,100,3),220,np.uint8);frame[50,20]=0
        c=self.controller(frame);c.wheel=lambda *a,**k:self.fail('single region should not zoom when target is visible')
        c.drag=lambda *a,**k:self.fail('single region should not drag when target is visible')
        result=_collect(c,None)
        self.assertIsNone(result)
        self.assertEqual(len(c.single_candidates),1)
        self.assertAlmostEqual(c.single_candidates[0]['matrix'][0,2],5.)
        self.assertIsNone(c.samples)

    def test_single_search_executes_visible_candidate_and_stops_on_actual_match(self):
        from screenshot_live import _search
        from screenshot_search import actual_result
        frame=np.full((100,100,3),220,np.uint8);frame[50,20]=0
        c=self.controller(frame);c.single_candidates=[]
        moved=[]
        c.move_to=lambda matrix,*a,**k:moved.append(matrix) or True
        c.observe=lambda *a,**k:actual_result(['#000000',None,None],single_rules())
        c.restore=lambda:None
        result=_search(c,None)
        self.assertIsNone(result)
        self.assertEqual(len(moved),1)

    def test_single_missing_target_uses_one_bounded_exploration_view(self):
        from screenshot_live import _collect
        frame=np.full((100,100,3),220,np.uint8);c=self.controller(frame)
        calls=[]
        def wheel(steps,label):calls.append((steps,label));c.frame=np.full_like(frame,220);return None
        c.wheel=wheel;c.drag=lambda *a,**k:self.fail('single fallback should not scan full rows')
        _collect(c,None)
        self.assertLessEqual(len(calls),2)

    def test_first_zoom_reveals_target_and_stops_before_any_scan_or_model(self):
        from screenshot_live import _collect,_search
        from screenshot_search import actual_result
        c=self.controller(np.full((100,100,3),220,np.uint8));wheels=[];moves=[]
        def wheel(steps,label):
            wheels.append(steps);c.pose[:2,:2]*=.99**abs(steps)
            c.frame=np.full((100,100,3),220,np.uint8);c.frame[50,20]=0
        c.wheel=wheel;c.drag=lambda *a,**k:self.fail('No full scan should follow a revealed target')
        c.move_to=lambda matrix,*a,**k:moves.append(matrix) or True
        def read(*a,**k):
            c.current=actual_result(['#000000',None,None],single_rules());return c.current
        c.observe=read;c.restore=lambda:c.current
        with patch('screenshot_live.RawSamples',side_effect=AssertionError('No model needed')):
            samples=_collect(c,None);self.assertIsNone(_search(c,samples))
        self.assertEqual(wheels,[-25]);self.assertEqual(len(moves),1)
        self.assertTrue(c.current['accepted']);self.assertIsNone(c.samples)

    def test_single_similarity_uses_alternatives_and_the_selected_regions_tolerance(self):
        from screenshot_single import candidates
        c=self.controller(np.full((100,100,3),220,np.uint8))
        c.rules[0]['enabled']=False;c.rules[2].update(enabled=True,colors=['#010101','#FFFFFF'],exact=False,tolerance=1.)
        c.frame[50,65]=255
        rows=candidates(c)
        self.assertEqual(rows[0]['region'],2);self.assertEqual(rows[0]['observed_rgb'],[255]*3)

    def test_retry_explores_before_testing_the_previous_view(self):
        from screenshot_live import _collect,_search
        from screenshot_search import actual_result
        c=self.controller(np.full((100,100,3),220,np.uint8));c.frame[50,20]=0;c.single_retry=True
        calls=[]
        def wheel(steps,label):calls.append('zoom');c.pose[:2,:2]*=.99**25
        c.wheel=wheel;c.move_to=lambda *a,**kw:calls.append('position') or True
        c.observe=lambda *a,**kw:actual_result(['#000000',None,None],single_rules())
        c.restore=lambda:None
        _collect(c,None);_search(c,None)
        self.assertEqual(calls,['zoom','position'])

if __name__=='__main__':unittest.main()
