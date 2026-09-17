import unittest
import numpy as np
from unittest.mock import patch
import threading
from platform_win import Game,Interrupted
from vision import accepted,normalize_hex,candidate_shift,Scene

class MatchingTests(unittest.TestCase):
    def rule(self,colors,exact=True,tolerance=8):return {'enabled':True,'colors':colors,'exact':exact,'tolerance':tolerance}
    def test_exact_rejects_one_channel_difference(self):
        rules=[self.rule(['#202020'])]*3
        self.assertFalse(accepted(['#202021','#202020','#202020'],rules))
        self.assertTrue(accepted(['#202020']*3,rules))
    def test_alternative_and_disabled(self):
        self.assertTrue(accepted(['#FFFFFF',None,None],[self.rule(['#202020','#FFFFFF']),{'enabled':False},{'enabled':False}]))
    def test_incomplete_enabled_rejected(self):
        self.assertFalse(accepted([None,None,None],[self.rule(['#FFFFFF']),{'enabled':False},{'enabled':False}]))
    def test_invalid_hex(self):
        for s in ['#1234567','red','#GG0000','']:
            with self.assertRaises(ValueError):normalize_hex(s)
    def test_joint_translation_respects_independent_thirds(self):
        im=np.full((300,300,3),[150,150,150],dtype=np.uint8)
        points=[(50,100),(150,150),(250,200)];targets=['#E02030','#20E030','#2030E0']
        from vision import rgb
        for (x,y),color in zip(points,targets):im[y+20-2:y+20+3,x-15-2:x-15+3]=rgb(color)
        scene=Scene([],points,(0,0,300,300),targets,120,None)
        dx,dy,score=candidate_shift(im,scene,[self.rule([c]) for c in targets])
        self.assertLessEqual(abs(dx-15),2);self.assertLessEqual(abs(dy+20),2);self.assertLess(score,1)
    def test_white_target_is_not_filtered_as_ui(self):
        im=np.full((300,300,3),[100,80,70],dtype=np.uint8)
        im[175:185,65:75]=255
        scene=Scene([],[(50,150),(150,150),(250,150)],(0,0,300,300),[None]*3,120,None)
        move=candidate_shift(im,scene,[self.rule(['#FFFFFF']),{'enabled':False},{'enabled':False}])
        self.assertIsNotNone(move)
        self.assertEqual(move[2],0)
        self.assertTrue(-25<=move[0]<=-15 and -35<=move[1]<=-25)

    def test_single_pixel_target_on_large_board_far_from_marker(self):
        im=np.full((900,900,3),80,dtype=np.uint8)
        im[55,77]=255
        scene=Scene([],[(150,800),(450,500),(750,500)],(0,0,900,900),[None]*3,120,None)
        move=candidate_shift(im,scene,[self.rule(['#FFFFFF']),{'enabled':False},{'enabled':False}])
        self.assertEqual(move,(73,745,0.0))

    def test_interrupted_drag_releases_left_button(self):
        game=Game.__new__(Game);events=[]
        game.move_to=lambda p:None;game.send=lambda flag,*a,**kw:events.append(flag)
        calls=[0]
        def check():
            calls[0]+=1
            if calls[0]>2:raise Interrupted('stop')
        game.check=check
        with patch('platform_win.time.sleep',return_value=None):
            with self.assertRaises(Interrupted):game.path([(0,0),(1,1),(2,2),(3,3)])
        self.assertEqual(events[0],2);self.assertEqual(events[-1],4)
        self.assertEqual(events.count(1),1)
    def test_interrupted_rotation_releases_right_button(self):
        game=Game.__new__(Game);events=[]
        game.move_to=lambda p:None;game.send=lambda flag,*a,**kw:events.append(flag)
        n=[0]
        def check():
            n[0]+=1
            if n[0]>1:raise Interrupted('stop')
        game.check=check
        with patch('platform_win.time.sleep',return_value=None):
            with self.assertRaises(Interrupted):game.path([(0,0),(1,1)],right=True)
        self.assertEqual(events,[8,16])

    def test_zoom_burst_preserves_anchor_and_can_stop_midway(self):
        game=Game.__new__(Game);events=[];positions=[];checks=[0]
        game.move_to=positions.append;game.send=lambda flags,**kw:events.append((flags,kw))
        def check():
            checks[0]+=1
            if checks[0]==5:raise Interrupted('stop')
        game.check=check
        with patch('platform_win.time.sleep'):
            with self.assertRaises(Interrupted):game.wheel((0,0,300,300),24,anchor=(70,80))
        self.assertEqual(positions,[(70,80)])
        self.assertEqual(len(events),3)
        self.assertTrue(all(e==(0x800,{'data':120}) for e in events))

    def test_one_pixel_drag_has_no_zero_move_events(self):
        game=Game.__new__(Game);events=[];positions=[];game.check=lambda:None;game.move_to=positions.append
        game.send=lambda flag,dx=0,dy=0:events.append((flag,dx,dy))
        with patch('platform_win.time.sleep'):game.drag((0,0,300,300),0,-1)
        self.assertEqual(len(positions),2)
        self.assertEqual((positions[1][0]-positions[0][0],positions[1][1]-positions[0][1]),(0,-1))
        self.assertEqual([e[0] for e in events],[2,4])

    def test_rotation_presses_at_requested_pivot_then_traces_safe_arc(self):
        game=Game.__new__(Game);record=[]
        game.path=lambda points,**kwargs:record.append((points,kwargs))
        game.rotate((0,0,500,400),60,anchor=(115,270))
        points,options=record[0]
        self.assertEqual(points[0],(115,270))
        self.assertTrue(options['right']);self.assertTrue(options['absolute'])
        radii=[np.linalg.norm(np.array(p)-[115,270]) for p in points[8:]]
        self.assertLess(max(radii)-min(radii),1.5)
        self.assertTrue(all(0<x<500 and 0<y<400 for x,y in points))

    def test_small_angle_at_edge_uses_long_arc(self):
        from platform_win import rotation_path
        pivot=np.array([60,340]);points=rotation_path((0,0,400,400),pivot,.4)
        start=np.array(points[8])-pivot;end=np.array(points[-1])-pivot
        measured=np.degrees(np.arctan2(start[0]*end[1]-start[1]*end[0],np.dot(start,end)))
        self.assertGreater(np.linalg.norm(start),250)
        self.assertLess(abs(measured-.4),.2)
        self.assertTrue(all(0<x<400 and 0<y<400 for x,y in points))

if __name__=='__main__':unittest.main()
