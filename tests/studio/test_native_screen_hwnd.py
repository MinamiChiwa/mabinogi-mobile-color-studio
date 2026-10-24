"""The native screen's HWND belongs to the input-coordinate binding."""
import struct,unittest
from native_live.read_unity_screen import read_unity_screen_extent
from native_live.read_native_rect import SUPPORTED_UNITYPLAYER


class ScreenReader:
    def __init__(self):self.base=0x10000;self.state=0x20000;self.hwnd=331176
    def read(self,address,size):
        values={self.base+0x1b23390:struct.pack('<Q',self.state),
            self.state+0xe0:struct.pack('<Q',self.hwnd),
            self.state+0xfc:struct.pack('<i',1280),self.state+0x108:struct.pack('<i',960)}
        return values[address]


class NativeScreenWindowTests(unittest.TestCase):
    def test_native_window_handle_is_repeated_and_recorded(self):
        reader=ScreenReader();result=read_unity_screen_extent(reader,reader.base,unityplayer_sha256=SUPPORTED_UNITYPLAYER)
        self.assertEqual(result.get('hwnd'),331176)
    def test_changed_native_handle_cannot_pass_a_stable_screen_read(self):
        reader=ScreenReader();original=reader.read;count=[0]
        def read(address,size):
            if address==reader.state+0xe0:
                count[0]+=1
                if count[0]>1:return struct.pack('<Q',reader.hwnd+1)
            return original(address,size)
        reader.read=read
        with self.assertRaisesRegex(ValueError,'changed'):
            read_unity_screen_extent(reader,reader.base,unityplayer_sha256=SUPPORTED_UNITYPLAYER)


if __name__=='__main__':unittest.main()
