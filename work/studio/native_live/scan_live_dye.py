"""Preflight bounded scan for valid dye instances and live Unity native textures."""
import struct,sys,time,json,datetime
from pathlib import Path
from .runtime_read import Reader
from .capture_dye_state import checked_object, mm_items, snapshot
def inspect(r,a,cls):
 if r.u64(a)!=cls or r.u64(a+8)!=0:return None
 fs=checked_object(r,a,'MM.Client.Presentation.UI.Instances.StageScene.Dyeing.DyeingPaletteInstanceImpl')
 data=r.u64(a+fs['data']);df=checked_object(r,data,'Client.CodeGenerated.UI.DyeingPaletteControlData')
 result=r.u64(a+fs['resultCache']);checked_object(r,result,'Client.CodeGenerated.UI.DyeingPaletteResult')
 arr,count=mm_items(r,r.u64(data+df['PaletteFragmentDataList']))
 natives=[]
 for i in range(count):
  f=r.u64(arr+32+i*8);ff=checked_object(r,f,'Client.CodeGenerated.UI.DyeingPaletteFragmentData');texture=r.u64(f+ff['Texture'])
  if r.class_name(r.u64(texture))!='UnityEngine.Texture2D':return None
  natives.append(r.u64(texture+16))
 controller=r.u64(a+fs['<TransitionController>k__BackingField']);state=struct.unpack('<i',r.read(controller+20,4))[0]
 material=r.u64(data+df['SharedMaterial']);native_material=r.u64(material+16)
 active_result=r.u64(a+fs['<Result>k__BackingField'])
 return {'address':hex(a),'data':hex(data),'region_count':count,'native_textures':[hex(x) for x in natives],'live_textures':all(natives),'native_material':hex(native_material),'controller_state':state,'active_result':hex(active_result),'capture_eligible':all(natives) and bool(native_material) and bool(active_result) and state==2}
def scan(r,capture=False):
 cls=r.u64(r.base+0x106c9010);pattern=struct.pack('<Q',cls);hits=[];saved=[];seen=set();total=0;t=time.perf_counter()
 for region in r.regions():
  if region.State!=0x1000 or region.Type!=0x20000 or region.Protect&0x100 or region.Protect&0xff not in (4,8,0x40,0x80):continue
  for start in range(region.BaseAddress,region.BaseAddress+region.RegionSize,8*1024*1024):
   length=min(8*1024*1024+8,region.BaseAddress+region.RegionSize-start)
   try:b=r.read(start,length)
   except OSError:continue
   total+=len(b);pos=0
   while True:
    pos=b.find(pattern,pos)
    if pos<0:break
    a=start+pos;pos+=8
    if a%8 or a in seen:continue
    seen.add(a)
    try:h=inspect(r,a,cls)
    except (OSError,ValueError,struct.error):continue
    if h:
     hits.append(h);print('CANDIDATE',json.dumps(h),flush=True)
     if capture and h['capture_eligible']:
      try:
       dest,record=snapshot(r,a,'live_candidate');saved.append(str(dest));print('SAVED',dest,flush=True)
      except (OSError,ValueError,struct.error) as e:print('RETRY_NEEDED',str(e),flush=True)
      if saved:return hits,saved,total,time.perf_counter()-t
 return hits,saved,total,time.perf_counter()-t
