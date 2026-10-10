"""Dye-only read-only snapshot. No writes to process memory or game files."""
import sys,struct,json,hashlib,time,datetime
from pathlib import Path
import numpy as np
from PIL import Image
from .runtime_read import Reader
OUTROOT=Path('outputs/runtime_captures')
def checked_object(r,address,expected):
 cls=r.u64(address);name=r.class_name(cls)
 if name!=expected:raise ValueError(f'Unexpected object type: {name}')
 return r.fields(cls)
def mm_items(r,address,max_count=32):
 if r.class_name(r.u64(address))!='Silvervine.ManualMemory.MMList`1':raise ValueError('Not an MMList')
 array=r.u64(address+16);count=struct.unpack('<i',r.read(address+28,4))[0]
 length=r.u64(array+24)
 if not(0<count<=max_count and count<=length<=100000):raise ValueError('Invalid MMList size')
 return array,count
def snapshot(r,address,tag,*,output_root=None):
 fs=checked_object(r,address,'MM.Client.Presentation.UI.Instances.StageScene.Dyeing.DyeingPaletteInstanceImpl')
 data=r.u64(address+fs['data']);result=r.u64(address+fs['resultCache']);active_result=r.u64(address+fs['<Result>k__BackingField'])
 df=checked_object(r,data,'Client.CodeGenerated.UI.DyeingPaletteControlData')
 checked_object(r,result,'Client.CodeGenerated.UI.DyeingPaletteResult')
 before=r.read(result+16,16);px,py,scale,rotation=struct.unpack('<4f',before)
 if not all(np.isfinite([px,py,scale,rotation])) or not .0001<scale<10000:raise ValueError('Invalid view state')
 fragment_list=r.u64(data+df['PaletteFragmentDataList']);array,count=mm_items(r,fragment_list)
 fragments=[];payloads=[];pixel_reads=[]
 for i in range(count):
  fragment=r.u64(array+32+i*8);ff=checked_object(r,fragment,'Client.CodeGenerated.UI.DyeingPaletteFragmentData')
  palette=r.u64(fragment+ff['Palette']);pf=checked_object(r,palette,'Shared.DyePalette.DyePalette')
  width=struct.unpack('<i',r.read(palette+pf['Width'],4))[0];height=struct.unpack('<i',r.read(palette+pf['Height'],4))[0];channels=struct.unpack('<i',r.read(palette+pf['Channels'],4))[0]
  if (width,height,channels)!=(254,254,3):raise ValueError('Unexpected dye palette dimensions')
  raw_array=r.u64(palette+pf['Data']);length=r.u64(raw_array+24)
  if length!=width*height*channels:raise ValueError('Invalid dye byte array size')
  raw=r.read(raw_array+32,length);pixels=np.frombuffer(raw,np.uint8).reshape(height,width,channels)[::-1].copy()
  pixel_reads.append((raw_array+32,length,hashlib.sha256(raw).digest()))
  endpoint=struct.unpack('<f',r.read(fragment+ff['NormalizedPositionY'],4))[0]
  if not 0<=endpoint<=1:raise ValueError('Invalid picker position')
  fragments.append({'index':i,'resource_object':hex(palette),'width':width,'height':height,'channels':channels,'normalized_picker_y':endpoint,'pixel_file':f'fragment_{i}.png','raw_sha256':hashlib.sha256(raw).hexdigest()});payloads.append(pixels)
 colors_addr=r.u64(address+fs['colorPickerColors']);color_array,color_count=mm_items(r,colors_addr)
 colors=struct.unpack('<'+'f'*(color_count*4),r.read(color_array+32,color_count*16));colors=[list(colors[i*4:i*4+4]) for i in range(color_count)]
 if color_count!=count or not np.all(np.isfinite(colors)):raise ValueError('Picker count or color data invalid')
 for ptr,length,digest in pixel_reads:
  if hashlib.sha256(r.read(ptr,length)).digest()!=digest:raise ValueError('Palette pixels changed during capture; retry')
 after=r.read(result+16,16)
 if before!=after or data!=r.u64(address+fs['data']) or active_result!=r.u64(address+fs['<Result>k__BackingField']):raise ValueError('State changed during capture; retry')
 ratio=struct.unpack('<f',r.read(data+df['ColorPreserveRatio'],4))[0]
 stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
 dest=(Path(output_root) if output_root is not None else OUTROOT)/(stamp+'_'+tag);dest.mkdir(parents=True,exist_ok=False)
 for fragment,pixels in zip(fragments,payloads):Image.fromarray(pixels).save(dest/fragment['pixel_file'])
 record={'schema_version':1,'captured_at_utc':stamp,'capture_read_seconds':None,'pid':r.pid,'instance_address':hex(address),'source':'runtime_active_candidate' if active_result else 'runtime_retained_session_unattributed','active_result_pointer':hex(active_result),'position':[px,py],'scale':scale,'rotation_degrees':rotation,'color_preserve_ratio':ratio,'fragments':fragments,'picker_colors_rgba':colors,'state_stable_during_read':True,'pixel_orientation':'saved top-down RGB PNG; runtime byte array is bottom-up RGB','note':'Captured client dye pixels; no swap replay is needed. Result-pointer state alone does not prove current UI visibility or session attribution.'}
 (dest/'snapshot.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
 return dest,record
