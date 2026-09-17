import unittest,ctypes,threading
from ctypes import wintypes as W
from unittest.mock import MagicMock
from hotkeys import KeyEdges,run_hotkeys

class HotkeyTests(unittest.TestCase):
    def test_message_and_poll_fire_once_for_one_press(self):
        edges=KeyEdges()
        self.assertTrue(edges.accept(1,1))
        self.assertFalse(edges.poll(1,True,1.02))
        self.assertFalse(edges.poll(1,True,2))
        self.assertFalse(edges.poll(1,False,2.1))
        self.assertTrue(edges.poll(1,True,2.2))
    def test_poll_then_message_is_deduplicated(self):
        edges=KeyEdges();self.assertTrue(edges.poll(2,True,1));self.assertFalse(edges.accept(2,1.01))
    def test_failed_registration_is_not_polled_or_unregistered(self):
        user=MagicMock();stop=threading.Event();events=[]
        user.RegisterHotKey.side_effect=[True,False];user.PeekMessageW.return_value=False
        user.GetAsyncKeyState.return_value=0
        def wait(_):stop.set()
        stop.wait=wait
        run_hotkeys(user,ctypes,W,stop,lambda k,d:events.append((k,d)),[(1,0x77),(2,0x78)])
        user.GetAsyncKeyState.assert_called_once_with(0x77)
        user.UnregisterHotKey.assert_called_once_with(None,1)
        self.assertEqual(events[0][1]['failed'],[2])
