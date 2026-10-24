"""Build-bound native legacy mouse cache is diagnostic, not a fresh input oracle."""
import importlib
import importlib.util
import struct
import unittest


class Reader:
    def __init__(self):
        self.guard=lambda:None;self.base=0x180000000;self.state=0x200000000
        self.changed=False;self.cache_reads=0
    def read(self,address,size):
        self.guard()
        if address==self.base+0x1ae5628:return struct.pack('<Q',self.state)
        if address==self.state+0xc8:
            self.cache_reads+=1
            return struct.pack('<2f',100.,201. if self.changed and self.cache_reads>1 else 200.)
        raise ValueError('Unexpected diagnostic address')


class NativeMouseDiagnosticTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('native_live.read_native_mouse_diagnostic'),'Native mouse diagnostic missing')
        return importlib.import_module('native_live.read_native_mouse_diagnostic')
    def test_native_cache_is_repeated_and_never_labeled_fresh(self):
        reader=Reader();module=self.module()
        result=module.read_native_mouse_cache(reader,reader.base,module.SUPPORTED_UNITYPLAYER,10.,clock=lambda:0.)
        self.assertEqual(result['cached_mouse_unity'],[100.,200.])
        self.assertTrue(result['repeat_values_equal'])
        self.assertFalse(result['freshness_verified']);self.assertFalse(result['ready_for_input'])
        self.assertEqual(result['inputs_sent'],0);self.assertEqual(reader.cache_reads,2)
    def test_changed_cache_returns_unknown_diagnostic(self):
        reader=Reader();reader.changed=True;module=self.module()
        result=module.read_native_mouse_cache(reader,reader.base,module.SUPPORTED_UNITYPLAYER,10.,clock=lambda:0.)
        self.assertFalse(result['stable_read']);self.assertFalse(result['freshness_verified'])
        self.assertEqual(result['status'],'cache_changed_during_read')
    def test_unknown_build_never_reads_memory(self):
        reader=Reader();module=self.module()
        result=module.read_native_mouse_cache(reader,reader.base,'unknown',10.,clock=lambda:0.)
        self.assertEqual(result['status'],'unsupported_build');self.assertEqual(reader.cache_reads,0)
    def test_f9_check_propagates_and_restores_reader_guard(self):
        reader=Reader();module=self.module();prior=reader.guard
        def stop():raise InterruptedError('F9')
        with self.assertRaises(InterruptedError):module.read_native_mouse_cache(reader,reader.base,
          module.SUPPORTED_UNITYPLAYER,10.,check=stop,clock=lambda:0.)
        self.assertIs(reader.guard,prior)


if __name__=='__main__':unittest.main()
