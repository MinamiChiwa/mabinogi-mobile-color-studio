"""Preflight bounded scan for valid dye instances and live Unity native textures."""
import struct,sys,time,json,datetime
from pathlib import Path
from .runtime_read import Reader
from .capture_dye_state import checked_object, mm_items, snapshot


class IncrementalDyeScan:
 """Resume a guarded heap census; a partial first hit is never a selection.

 A slice retains its current bytes/find cursor and every aligned class match,
 including inactive or temporarily uninitialized objects. All matches are
 inspected again after the census before uniqueness can be established.
 """
 def __init__(self,reader,cls,*,clock=time.monotonic,known_addresses=()):
  self.reader=reader;self.cls=cls;self.clock=clock;self.started=clock()
  self.pattern=struct.pack('<Q',cls);self.regions=iter(reader.regions())
  self.region=None;self.next_address=None;self.buffer=None;self.buffer_start=None;self.find_position=0
  self.seen=set();self.hits={};self.first_eligible_seen={};self.known=list(known_addresses);self.known_index=0
  self.validation_addresses=None;self.validation_index=0;self.validated={}
  self.phase='scanning';self.bytes_scanned=0;self.chunks_scanned=0;self.regions_visited=0
  self.read_failures=0;self.last_read_error=None;self.candidate_read_errors={}

 def _inspect(self,address,check,*,validating=False):
  check();began=self.clock();unreadable=False
  try:hit=inspect(self.reader,address,self.cls)
  except (InterruptedError,TimeoutError):raise
  except OSError as exc:
   check();hit=None;unreadable=True
   self.candidate_read_errors[address]=type(exc).__name__+': '+str(exc)
  except (ValueError,struct.error):
   check();hit=None
  check()
  if hit:
   self.hits[address]=hit
   if hit['capture_eligible']:self.first_eligible_seen.setdefault(address,began)
  if validating:
   # A final read error leaves an unknown object. It cannot be used as proof
   # of absence; an earlier transient error clears only after this recheck.
   if not unreadable:self.candidate_read_errors.pop(address,None)
   if hit:self.validated[address]=hit
   else:self.validated.pop(address,None)
  return hit

 def advance(self,deadline,check,*,slice_seconds=.25,max_bytes=64*1024*1024,max_candidates=128):
  """Yield at operation boundaries; caller's guard remains on every read."""
  check();slice_end=min(deadline,self.clock()+slice_seconds);read_bytes=0;inspected=0;visited=0
  while self.phase!='complete' and self.clock()<slice_end and read_bytes<max_bytes and inspected<max_candidates and visited<256:
   check()
   if self.known_index<len(self.known):
    # Early observations improve age diagnostics, never authorize a partial census.
    self._inspect(self.known[self.known_index],check)
    self.known_index+=1;inspected+=1;continue
   if self.phase=='validating':
    if self.validation_index>=len(self.validation_addresses):
     self.phase='complete';continue
    address=self.validation_addresses[self.validation_index]
    self._inspect(address,check,validating=True)
    self.validation_index+=1;inspected+=1;continue
   if self.buffer is not None:
    position=self.buffer.find(self.pattern,self.find_position)
    if position<0:
     self.buffer=None;continue
    address=self.buffer_start+position
    if address%8 or address in self.seen:
     self.find_position=position+8;continue
    # Commit the cursor only after the guarded inspection finishes. An outer
    # cancellation/deadline cannot discard a candidate or the remaining buffer.
    self._inspect(address,check);self.seen.add(address)
    self.find_position=position+8;inspected+=1;continue
   if self.region is None or self.next_address>=self.region.BaseAddress+self.region.RegionSize:
    try:region=next(self.regions)
    except StopIteration:
     self.phase='validating'
     self.validation_addresses=sorted(self.seen|set(self.known));continue
    self.regions_visited+=1;visited+=1
    if region.State!=0x1000 or region.Type!=0x20000 or region.Protect&0x100 or region.Protect&0xff not in (4,8,0x40,0x80):
     self.region=None;continue
    self.region=region;self.next_address=region.BaseAddress
   start=self.next_address
   length=min(8*1024*1024+8,self.region.BaseAddress+self.region.RegionSize-start)
   try:buffer=self.reader.read(start,length)
   except (InterruptedError,TimeoutError):raise
   except OSError as exc:
    check();self.read_failures+=1;self.last_read_error=type(exc).__name__+': '+str(exc)
    self.next_address+=8*1024*1024;continue
   check()
   if len(buffer)!=length:
    self.read_failures+=1;self.last_read_error='Short process read'
    self.next_address+=8*1024*1024;continue
   self.buffer=buffer;self.buffer_start=start;self.find_position=0
   self.next_address+=8*1024*1024
   self.bytes_scanned+=len(buffer);read_bytes+=len(buffer);self.chunks_scanned+=1
  return self.diagnostic()

 def diagnostic(self):
  rows=self.validated if self.phase=='complete' else self.hits
  eligible=sorted(address for address,hit in rows.items() if hit['capture_eligible'])
  complete=self.phase=='complete' and self.read_failures==0 and not self.candidate_read_errors
  return dict(status='coverage_incomplete' if self.phase=='complete' and not complete else self.phase,
   scan_complete=complete,heap_scan_complete=self.phase in ('validating','complete'),
   uniqueness_verified=complete and len(eligible)==1,
   regions_visited=self.regions_visited,chunks_scanned=self.chunks_scanned,bytes_scanned=self.bytes_scanned,
   candidate_count=len(self.seen|set(self.known)),typed_candidate_count=len(rows),
   eligible_addresses=[hex(address) for address in eligible],
   first_eligible_seen_monotonic=min((self.first_eligible_seen[address] for address in eligible),default=None),
   read_failures=self.read_failures,last_read_error=self.last_read_error,
   candidate_read_failures=len(self.candidate_read_errors),
   unreadable_candidate_addresses=[hex(address) for address in sorted(self.candidate_read_errors)],
   candidate_read_errors={hex(address):error for address,error in sorted(self.candidate_read_errors.items())},
   scan_started_monotonic=self.started,scan_elapsed_seconds=max(0.,self.clock()-self.started),
   inputs_sent=0,ready_for_input=False)

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
