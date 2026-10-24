"""Controlled MMList memory contracts; these tests never open a process."""
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from native_live import capture_dye_state as capture
from native_live import native_provider_backend as provider


class DyeMemory:
    def __init__(self, count=2, color_count=None, gradient=False):
        self.pid=17;self.guard=lambda:None;self.base=0x100000000
        self.memory=bytearray(2_000_000);self.next=16;self.classes={};self.on_read=None
        self.instance=self.object('MM.Client.Presentation.UI.Instances.StageScene.Dyeing.DyeingPaletteInstanceImpl',
            dict(resultCache=16,data=24,**{'<Result>k__BackingField':32},colorPickerColors=40,
                 **{'<TransitionController>k__BackingField':48}))
        self.data=self.object('Client.CodeGenerated.UI.DyeingPaletteControlData',
            dict(PaletteFragmentDataList=16,ColorPreserveRatio=24,SharedMaterial=32))
        self.result=self.object('Client.CodeGenerated.UI.DyeingPaletteResult',{})
        self.put(self.result+16,'4f',0.,0.,1.,0.)
        self.put(self.instance+16,'QQQ',self.result,self.data,self.result)
        transition=self.allocate(64);self.put(transition+20,'i',2)
        self.put(self.instance+48,'Q',transition)
        material=self.allocate(64);self.put(material+16,'Q',0x700000000)
        self.put(self.data+32,'Q',material)
        self.fragments=[];self.palettes=[];self.raw_arrays=[]
        for index in range(count):
            fragment=self.object('Client.CodeGenerated.UI.DyeingPaletteFragmentData',
                dict(Palette=16,NormalizedPositionY=24,Texture=32))
            palette=self.object('Shared.DyePalette.DyePalette',dict(Width=16,Height=20,Channels=24,Data=32))
            pixels=np.full((254,254,3),(64,128,192),np.uint8)
            if gradient:pixels[:,:,0]=np.arange(254,dtype=np.uint8)
            raw=self.allocate(32+pixels.nbytes);self.put(raw+24,'Q',pixels.nbytes)
            self.bytes(raw+32,pixels.tobytes())
            self.put(palette+16,'iii',254,254,3);self.put(palette+32,'Q',raw)
            texture=self.object('UnityEngine.Texture2D',{});self.put(texture+16,'Q',0x800000000+index*16)
            self.put(fragment+16,'Q',palette);self.put(fragment+24,'f',.5);self.put(fragment+32,'Q',texture)
            self.fragments.append(fragment);self.palettes.append(palette);self.raw_arrays.append(raw)
        self.fragment_list,self.fragment_array=self.list(self.fragments,struct.pack('<'+'Q'*count,*self.fragments))
        self.put(self.data+16,'Q',self.fragment_list)
        color_count=count if color_count is None else color_count
        colors=[(190 if i==0 else 63,128,192) if gradient else (64,128,192) for i in range(color_count)]
        rgba=[v for rgb in colors for v in (*(channel/255 for channel in rgb),1.)]
        self.color_list,self.color_array=self.list(range(color_count),struct.pack('<'+'f'*len(rgba),*rgba))
        self.put(self.instance+40,'Q',self.color_list)

    def allocate(self,size):
        address=self.base+self.next;self.next+=(size+15)//16*16
        return address

    def object(self,name,fields):
        if name not in self.classes:
            cls=self.allocate(256);namespace,_,short_name=name.rpartition('.')
            name_address=self.allocate(256);namespace_address=self.allocate(256)
            self.bytes(name_address,short_name.encode()+b'\0')
            self.bytes(namespace_address,namespace.encode()+b'\0')
            table=self.allocate(32*(len(fields)+1))
            self.put(cls+16,'QQ',name_address,namespace_address);self.put(cls+0x80,'Q',table)
            for index,(field,offset) in enumerate(fields.items()):
                field_address=self.allocate(256);self.bytes(field_address,field.encode()+b'\0')
                self.put(table+index*32,'QQQiI',field_address,0,cls,offset,0)
            self.classes[name]=(cls,fields)
        address=self.allocate(128);self.put(address,'Q',self.classes[name][0]);return address

    def list(self,items,payload):
        address=self.object('Silvervine.ManualMemory.MMList`1',{})
        array=self.allocate(32+max(64,len(payload)));self.put(array+24,'Q',len(items))
        self.bytes(array+32,payload);self.put(address+16,'Q',array);self.put(address+28,'i',len(items))
        return address,array

    def bytes(self,address,payload):
        index=address-self.base;self.memory[index:index+len(payload)]=payload

    def put(self,address,fmt,*values):self.bytes(address,struct.pack('<'+fmt,*values))

    def read(self,address,size):
        self.guard()
        if self.on_read is not None:self.on_read(address,size)
        index=address-self.base
        if index<0 or index+size>len(self.memory):raise ValueError('Outside fake memory')
        return bytes(self.memory[index:index+size])

    def u64(self,address):return struct.unpack('<Q',self.read(address,8))[0]

    def class_name(self,address):
        return next(name for name,(pointer,_) in self.classes.items() if pointer==address)

    def fields(self,address):
        return next(fields for pointer,fields in self.classes.values() if pointer==address)


def backend(reader,folder):
    result=object.__new__(provider.CurrentBuildBackend);result.reader=reader;result.output_root=Path(folder)
    result.exports=0;result.process_identity=lambda:(17,23,reader.base,'verified-build')
    def bind(check):
        reader.guard=check;check();return reader.u64(reader.instance)
    result._bind=bind
    return result


class NativeRegionReaderTests(unittest.TestCase):
    def test_probe_supports_two_and_three_real_fragment_lists(self):
        for count in (2,3):
            with self.subTest(count=count),tempfile.TemporaryDirectory() as folder:
                memory=DyeMemory(count);result=backend(memory,folder).probe(memory.instance,10.,lambda:None)
                self.assertTrue(result['active']);self.assertEqual(result.get('region_count'),count)
                self.assertEqual(len(result['session_token'][3]),count)
                self.assertEqual(len(result['session_token'][5]),count)

    def test_probe_rejects_unsupported_fragment_counts_and_mismatched_colors(self):
        for count,colors in ((1,1),(4,4),(2,3),(3,2)):
            with self.subTest(count=count,colors=colors),tempfile.TemporaryDirectory() as folder:
                memory=DyeMemory(count,color_count=colors)
                with self.assertRaises(ValueError):backend(memory,folder).probe(memory.instance,10.,lambda:None)

    def test_snapshot_records_physical_count_without_padding_or_deduplicating(self):
        for count in (2,3):
            with self.subTest(count=count),tempfile.TemporaryDirectory() as folder:
                memory=DyeMemory(count);path,record=capture.snapshot(memory,memory.instance,'test',output_root=folder)
                self.assertEqual(record.get('region_count'),count)
                self.assertEqual(len(record['fragments']),count);self.assertEqual(len(record['picker_colors_rgba']),count)
                self.assertEqual(len(list(path.glob('fragment_*.png'))),count)

    def test_snapshot_rejects_unsupported_layout_before_exporting(self):
        for count in (1,4):
            with self.subTest(count=count),tempfile.TemporaryDirectory() as folder:
                memory=DyeMemory(count)
                with self.assertRaises(ValueError):capture.snapshot(memory,memory.instance,'test',output_root=folder)
                self.assertEqual(list(Path(folder).iterdir()),[])

    def test_snapshot_rejects_list_or_ordered_identity_changes_during_capture(self):
        for mutation in ('fragment_count','fragment_array','fragment_identity','palette_identity',
                         'picker_y','color_count','color_array','color_payload','ratio'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as folder:
                memory=DyeMemory();fired=[False]
                def mutate(address,size):
                    if fired[0] or address!=memory.color_array+32:return
                    fired[0]=True
                    if mutation=='fragment_count':memory.put(memory.fragment_list+28,'i',1)
                    elif mutation=='fragment_array':memory.put(memory.fragment_list+16,'Q',memory.color_array)
                    elif mutation=='fragment_identity':memory.put(memory.fragment_array+32,'Q',memory.fragments[1])
                    elif mutation=='palette_identity':memory.put(memory.fragments[0]+16,'Q',memory.palettes[1])
                    elif mutation=='picker_y':memory.put(memory.fragments[0]+24,'f',.6)
                    elif mutation=='color_count':memory.put(memory.color_list+28,'i',1)
                    elif mutation=='color_array':memory.put(memory.color_list+16,'Q',memory.fragment_array)
                    elif mutation=='color_payload':
                        memory.on_read=None
                        old=memory.read(address,size)
                        # Mutate after the first read returns, when pixels are re-read.
                        def change_after_color(ptr,length):
                            if ptr==memory.raw_arrays[0]+32:memory.bytes(address,struct.pack('<f',.25)+old[4:]);memory.on_read=None
                        memory.on_read=change_after_color
                    elif mutation=='ratio':memory.put(memory.data+24,'f',.25)
                memory.on_read=mutate
                with self.assertRaises(ValueError):capture.snapshot(memory,memory.instance,'test',output_root=folder)
                self.assertEqual(list(Path(folder).iterdir()),[])

    def test_two_region_bundle_uses_quarter_and_three_quarter_picker_centers(self):
        with tempfile.TemporaryDirectory() as folder:
            memory=DyeMemory(gradient=True);result=backend(memory,folder).capture_validation_bundle(
                memory.instance,10.,lambda:None,clock=lambda:1.)
            self.assertEqual(result.get('region_count'),2)
            self.assertTrue(result['session_binding_verified'])
            self.assertTrue(result['cpu_comparison']['float_within_tolerance'])
            self.assertEqual(result['cpu_comparison']['predicted_hex'],['#BE80C0','#3F80C0'])
            self.assertEqual(result['cpu_comparison']['client_float_hex'],['#BE80C0','#3F80C0'])
            self.assertFalse(result['ready_for_input']);self.assertFalse(result['screenshot_hex_verified'])

    def test_bundle_rejects_changed_region_count_between_before_and_after_probe(self):
        with tempfile.TemporaryDirectory() as folder:
            memory=DyeMemory(3);live=backend(memory,folder)
            first=dict(live.probe(memory.instance,10.,lambda:None),region_count=3)
            changed=dict(first,region_count=2)
            with patch.object(live,'probe',side_effect=[first,changed]):
                with self.assertRaises(ValueError):live.capture_validation_bundle(memory.instance,10.,lambda:None,clock=lambda:1.)
            bindings=list(Path(folder).glob('*/validation_binding.json'))
            self.assertEqual(len(bindings),1)
            self.assertFalse(json.loads(bindings[0].read_text())['session_binding_verified'])

    def test_bundle_rejects_loaded_session_with_wrong_region_count(self):
        with tempfile.TemporaryDirectory() as folder:
            memory=DyeMemory(3);live=backend(memory,folder)
            malformed=dict(pixels=[np.full((254,254,3),(64,128,192),np.uint8)]*4,
                picker_uv=[[1/6,.5],[.5,.5],[5/6,.5]],color_preserve_ratio=0.)
            with patch.object(provider,'load_session',return_value=malformed):
                with self.assertRaises(ValueError):live.capture_validation_bundle(memory.instance,10.,lambda:None,clock=lambda:1.)


if __name__=='__main__':unittest.main()
