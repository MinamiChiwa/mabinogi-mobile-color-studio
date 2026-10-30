"""Preflight bounded scan for valid dye instances and live Unity native textures."""
import struct,sys,time,json,datetime
from collections import deque
import numpy as np
from pathlib import Path
from .runtime_read import Reader
from .capture_dye_state import checked_object, mm_items, snapshot


class InvalidDyeCandidate(ValueError):
 """A class byte-pattern match whose readable structure is not an object."""


def _pointer(value,field,*,nullable=False,class_pointer=False):
 if value==0 and nullable:return 0
 if type(value) is not int or not 0x10000<=value<0x800000000000 or value%8:
  raise InvalidDyeCandidate(f'Invalid {field} pointer: {value!r}')
 return value


class CandidateReadView:
 """Check scan-derived addresses before dereferencing, including metadata.

 Readable null, low, unaligned or noncanonical object links are invalid shapes.
 Read failures at structurally valid addresses still propagate as OSError.
 """
 def __init__(self,reader):self.reader=reader
 def read(self,address,size):
  if type(address) is not int or not 0x10000<=address<0x800000000000 or not 0<=size<=64*1024*1024 or address+size>0x800000000000:
   raise InvalidDyeCandidate(f'Invalid candidate read range: {address!r}, {size!r}')
  raw=self.reader.read(address,size)
  if len(raw)!=size:raise OSError(f'Short candidate read at {address:x}')
  return raw
 def u64(self,address):return struct.unpack('<Q',self.read(address,8))[0]
 def cstring(self,address,maxlen=256):return Reader.cstring(self,address,maxlen)
 def class_name(self,address):
  _pointer(address,'class',class_pointer=True)
  return Reader.class_name(self,address)
 def fields(self,address):
  _pointer(address,'class',class_pointer=True)
  _pointer(self.u64(address+0x80),'field table')
  return Reader.fields(self,address)


def _typed_object(reader,address,name,required=()):
 _pointer(address,name)
 _pointer(reader.u64(address),'class',class_pointer=True)
 if reader.class_name(reader.u64(address))!=name:
  raise InvalidDyeCandidate('Unexpected object type: '+name)
 if not required:return {}
 fields=reader.fields(reader.u64(address))
 if any(type(fields.get(key)) is not int or not 16<=fields[key]<=512 for key in required):
  raise InvalidDyeCandidate('Invalid runtime field layout: '+name)
 return fields


def _fragment_items(reader,address):
 _typed_object(reader,address,'Silvervine.ManualMemory.MMList`1')
 _pointer(reader.u64(address+16),'fragment array')
 return mm_items(reader,address)


class IncrementalDyeScan:
 """Resume a guarded heap census; a partial first hit is never a selection.

 A slice retains its current bytes/find cursor and every aligned class match,
 including inactive or temporarily uninitialized objects. All matches are
 inspected again after the census before uniqueness can be established.
 """
 aligned_search_min_bytes=64*1024
 def __init__(self,reader,cls,*,clock=time.monotonic,known_addresses=()):
  self.reader=reader;self.cls=cls;self.clock=clock;self.started=clock()
  self.pattern=struct.pack('<Q',cls)
  # Canonical x64 class pointers end in zero bytes. Searching the full needle
  # makes CPython's skip search visit almost every byte in zero-heavy heaps.
  # A nonzero-ending prefix locates possibilities cheaply; the full 8-byte
  # pointer is still checked locally before any match enters the census.
  self.search_pattern=self.pattern[:max(4,len(self.pattern.rstrip(b'\0')))]
  self.buffer_search_pattern=self.search_pattern;self.buffer_prefix_collisions=0
  self.prefix_collision_count=0;self.search_full_fallbacks=0
  self.regions=iter(reader.regions())
  self.region=None;self.next_address=None;self.buffer=None;self.buffer_start=None;self.find_position=0
  self.seen=set();self.hits={};self.first_eligible_seen={};self.known=list(known_addresses);self.known_index=0
  self.validation_addresses=None;self.validation_index=0;self.validated={}
  self.phase='scanning';self.bytes_scanned=0;self.chunks_scanned=0;self.regions_visited=0
  self.read_failures=0;self.last_read_error=None;self.candidate_read_errors={};self.rejected_candidates={}
  self.inactive_read_failures={};self.candidate_retries={}
  self.read_seconds=0.;self.search_seconds=0.;self.inspection_seconds=0.
  self.exact_search_blocks=0
  self.aligned_search_blocks=0;self.aligned_matches=None;self.aligned_window_end=0
  self.pending_reads=deque();self.unresolved_reads={}
  self.read_errors_seen=0;self.repaired_ranges=0;self.changed_ranges_excluded=0

 @staticmethod
 def _scan_region(region):
  return (region.State==0x1000 and region.Type==0x20000 and not region.Protect&0x100
          and region.Protect&0xff in (4,8,0x40,0x80))

 def _split_pending(self,start,length,cut):
  error=self.unresolved_reads.pop((start,length))
  for address,size in ((start,cut),(start+cut,length-cut)):
   self.unresolved_reads[address,size]=error
   self.pending_reads.append((address,size,0))

 def _failed_read(self,start,length,error,attempt):
  self.read_errors_seen+=1;self.last_read_error=str(error)
  self.unresolved_reads[start,length]=str(error)
  if attempt<1:
   self.pending_reads.append((start,length,attempt+1))
  elif length>4096:
   # Every possible object header is 8-byte aligned. Aligned splits preserve
   # all full headers without reading across an unreadable page boundary.
   self._split_pending(start,length,((length//2)//8)*8)

 def _inspect(self,address,check,*,validating=False):
  check();began=self.clock();unreadable=False
  try:hit=inspect(self.reader,address,self.cls)
  except (InterruptedError,TimeoutError):raise
  except OSError as exc:
   check();hit=None;unreadable=True
   error=type(exc).__name__+': '+str(exc)
   self.candidate_read_errors[address]=error
   # A dead UI instance may retain its class header after its data is freed.
   # Exclude it only with two readable, matching lifecycle witnesses. Unknown
   # or active objects remain blocking, including failures in this witness.
   try:
    inactive=_inactive_witness(self.reader,address,self.cls)
    check()
    if inactive and inactive==_inactive_witness(self.reader,address,self.cls):
     self.inactive_read_failures[address]=error;unreadable=False
   except (InterruptedError,TimeoutError):raise
   except (OSError,ValueError,struct.error):pass
  except InvalidDyeCandidate as exc:
   check();hit=None;self.rejected_candidates[address]=str(exc)
  except (ValueError,struct.error):
   check();hit=None
  finally:self.inspection_seconds+=max(0.,self.clock()-began)
  check()
  if hit:
   self.inactive_read_failures.pop(address,None)
   self.rejected_candidates.pop(address,None)
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
    # Retry only the unresolved candidate, never rescan gigabytes of heap.
    retries=self.candidate_retries.get(address,0)
    if address in self.candidate_read_errors and retries<2:
     self.candidate_retries[address]=retries+1;inspected+=1;continue
    self.validation_index+=1;inspected+=1;continue
   if self.buffer is not None:
    search_began=self.clock()
    if len(self.buffer)>=self.aligned_search_min_bytes:
     # Object headers are 8-byte aligned. Compare complete little-endian
     # pointers in bounded windows instead of searching every byte. Retain
     # both matches and the byte cursor so cancellation never loses a hit.
     if self.aligned_matches is None or self.find_position>=self.aligned_window_end:
      start=self.find_position+(-(self.buffer_start+self.find_position)%8)
      end=min(len(self.buffer),start+256*1024)
      count=max(0,(end-start)//8)
      if not count:
       self.buffer=None;continue
      self.aligned_window_end=start+count*8
      words=np.frombuffer(self.buffer,dtype='<u8',count=count,offset=start)
      self.aligned_matches=np.flatnonzero(words==self.cls)*8+start
     index=int(np.searchsorted(self.aligned_matches,self.find_position))
     if index==len(self.aligned_matches):
      self.find_position=self.aligned_window_end
      self.search_seconds+=max(0.,self.clock()-search_began)
      continue
     position=int(self.aligned_matches[index])
    else:position=self.buffer.find(self.buffer_search_pattern,self.find_position)
    exact=position>=0 and self.buffer.startswith(self.pattern,position)
    self.search_seconds+=max(0.,self.clock()-search_began)
    if position<0:
     self.buffer=None;continue
    address=self.buffer_start+position
    if not exact or address%8:
     # Prefix collisions and unaligned matches can overlap a real aligned
     # pointer. Advance one byte so none of those pointers are discarded.
     self.find_position=position+1
     if self.buffer_search_pattern!=self.pattern:
      self.buffer_prefix_collisions+=1;self.prefix_collision_count+=1
      if self.buffer_prefix_collisions>=32:
       # An atypical block packed with prefix collisions is cheaper to scan
       # with the exact needle. The committed byte cursor remains unchanged.
       self.buffer_search_pattern=self.pattern;self.search_full_fallbacks+=1
     continue
    if address in self.seen:
     self.find_position=position+8;continue
    # Commit the cursor only after the guarded inspection finishes. An outer
    # cancellation/deadline cannot discard a candidate or the remaining buffer.
    self._inspect(address,check);self.seen.add(address)
    self.find_position=position+8;inspected+=1;continue
   repairing=bool(self.pending_reads)
   if repairing:
    start,length,attempt=self.pending_reads.popleft();visited+=1
    query=getattr(self.reader,'query_region',None)
    if callable(query):
     try:
      check();current=query(start);check()
      base=current.BaseAddress or 0;extent=base+current.RegionSize
      if not base<=start<extent:raise OSError('Invalid repair memory range')
      if extent<start+length:
       self._split_pending(start,length,extent-start);continue
      if not self._scan_region(current):
       # Only an actual query can establish that a former scan page is no
       # longer eligible. Unresolved readable holes still block uniqueness.
       self.unresolved_reads.pop((start,length));self.changed_ranges_excluded+=1
       continue
     except (InterruptedError,TimeoutError):raise
     except OSError:
      check() # Try the read; a failed query alone cannot prove absence.
   elif self.region is None or self.next_address>=self.region.BaseAddress+self.region.RegionSize:
    try:region=next(self.regions)
    except StopIteration:
     self.phase='validating'
     self.validation_addresses=sorted(self.seen|set(self.known));continue
    except (InterruptedError,TimeoutError):raise
    except OSError as exc:
     # A failed region iterator is exhausted on its next call. Retain the
     # coverage failure so resuming cannot turn that exhaustion into proof.
     self.read_failures+=1;self.last_read_error=type(exc).__name__+': '+str(exc);check()
     raise
    self.regions_visited+=1;visited+=1
    if not self._scan_region(region):
     self.region=None;continue
    self.region=region;self.next_address=region.BaseAddress
   if not repairing:
    start=self.next_address
    length=min(8*1024*1024+8,self.region.BaseAddress+self.region.RegionSize-start)
    self.next_address+=8*1024*1024
   read_began=self.clock()
   try:
    buffer=self.reader.read(start,length)
    if len(buffer)!=length:raise OSError('Short process read')
   except (InterruptedError,TimeoutError):raise
   except OSError as exc:
    check();self._failed_read(start,length,type(exc).__name__+': '+str(exc),attempt if repairing else -1)
    continue
   finally:self.read_seconds+=max(0.,self.clock()-read_began)
   check()
   if repairing:
    self.unresolved_reads.pop((start,length));self.repaired_ranges+=1
   self.buffer=buffer;self.buffer_start=start;self.find_position=0
   self.aligned_matches=None;self.aligned_window_end=0
   self.aligned_search_blocks+=len(buffer)>=self.aligned_search_min_bytes
   # Prefix search wins on zero-heavy heaps but loses on already varied words.
   # A few bounded samples choose the needle only; every chosen match still
   # receives the exact full-pointer check below. No region is excluded.
   samples=(buffer[:4096],buffer[len(buffer)//2:len(buffer)//2+4096],buffer[-4096:])
   zero_density=sum(sample.count(0) for sample in samples)/max(1,sum(len(sample) for sample in samples))
   self.buffer_search_pattern=self.search_pattern if zero_density >= .5 else self.pattern
   self.exact_search_blocks += self.buffer_search_pattern==self.pattern
   self.buffer_prefix_collisions=0
   self.bytes_scanned+=len(buffer);read_bytes+=len(buffer);self.chunks_scanned+=1
  return self.diagnostic()

 def diagnostic(self):
  rows=self.validated if self.phase=='complete' else self.hits
  eligible=sorted(address for address,hit in rows.items() if hit['capture_eligible'])
  unresolved=self.read_failures+len(self.unresolved_reads)
  complete=self.phase=='complete' and unresolved==0 and not self.candidate_read_errors
  elapsed=max(0.,self.clock()-self.started)
  return dict(status='coverage_incomplete' if self.phase=='complete' and not complete else self.phase,
   scan_complete=complete,heap_scan_complete=self.phase in ('validating','complete'),
   uniqueness_verified=complete and len(eligible)==1,
   regions_visited=self.regions_visited,chunks_scanned=self.chunks_scanned,bytes_scanned=self.bytes_scanned,
   candidate_count=len(self.seen|set(self.known)),typed_candidate_count=len(rows),
   eligible_addresses=[hex(address) for address in eligible],
   first_eligible_seen_monotonic=min((self.first_eligible_seen[address] for address in eligible),default=None),
   read_failures=unresolved,last_read_error=self.last_read_error,
   read_errors_seen=self.read_errors_seen,repaired_ranges=self.repaired_ranges,
   changed_ranges_excluded=self.changed_ranges_excluded,pending_read_repairs=len(self.pending_reads),
   unresolved_read_ranges=[dict(address=hex(a),size=n,error=e)
                           for (a,n),e in list(self.unresolved_reads.items())[:16]],
   candidate_read_failures=len(self.candidate_read_errors),
   inactive_read_failures={hex(a):e for a,e in self.inactive_read_failures.items()},
   candidate_retries={hex(a):n for a,n in self.candidate_retries.items()},
   unreadable_candidate_addresses=[hex(address) for address in sorted(self.candidate_read_errors)],
   candidate_read_errors={hex(address):error for address,error in sorted(self.candidate_read_errors.items())},
   rejected_candidate_count=len(self.rejected_candidates),
   rejected_candidates={hex(address):reason for address,reason in sorted(self.rejected_candidates.items())[:16]},
   census_finished=self.phase=='complete',
   scan_started_monotonic=self.started,scan_elapsed_seconds=elapsed,
   search_pattern_bytes=len(self.search_pattern),read_seconds=self.read_seconds,
   prefix_collision_count=self.prefix_collision_count,search_full_fallbacks=self.search_full_fallbacks,
   exact_search_blocks=self.exact_search_blocks,
   aligned_search_blocks=self.aligned_search_blocks,
   search_seconds=self.search_seconds,inspection_seconds=self.inspection_seconds,
   throughput_mib_per_second=self.bytes_scanned/(1024*1024*elapsed) if elapsed>0 else 0.,
   inputs_sent=0,ready_for_input=False)

def _inactive_witness(reader,address,cls):
 r=CandidateReadView(reader)
 if r.u64(address)!=cls or r.u64(address+8)!=0:return None
 fields=_typed_object(r,address,'MM.Client.Presentation.UI.Instances.StageScene.Dyeing.DyeingPaletteInstanceImpl',
  ('<TransitionController>k__BackingField','<Result>k__BackingField'))
 controller=_pointer(r.u64(address+fields['<TransitionController>k__BackingField']),'transition controller')
 state=struct.unpack('<i',r.read(controller+20,4))[0]
 result=r.u64(address+fields['<Result>k__BackingField'])
 # State 2 is the only verified active state. An absent result alone is not
 # enough: the object may be activating while its data is being constructed.
 return (controller,state,result) if state==0 and result==0 else None


def inspect(r,a,cls):
 r=CandidateReadView(r)
 _pointer(a,'candidate');_pointer(cls,'dye class',class_pointer=True)
 if r.u64(a)!=cls or r.u64(a+8)!=0:return None
 fs=_typed_object(r,a,'MM.Client.Presentation.UI.Instances.StageScene.Dyeing.DyeingPaletteInstanceImpl',
  ('data','resultCache','<TransitionController>k__BackingField','<Result>k__BackingField'))
 data=_pointer(r.u64(a+fs['data']),'control data')
 df=_typed_object(r,data,'Client.CodeGenerated.UI.DyeingPaletteControlData',('PaletteFragmentDataList','SharedMaterial'))
 result=_pointer(r.u64(a+fs['resultCache']),'result cache')
 _typed_object(r,result,'Client.CodeGenerated.UI.DyeingPaletteResult')
 arr,count=_fragment_items(r,_pointer(r.u64(data+df['PaletteFragmentDataList']),'fragment list'))
 natives=[]
 for i in range(count):
  f=_pointer(r.u64(arr+32+i*8),'fragment')
  ff=_typed_object(r,f,'Client.CodeGenerated.UI.DyeingPaletteFragmentData',('Texture',))
  texture=_pointer(r.u64(f+ff['Texture']),'texture',nullable=True)
  if texture:
   _typed_object(r,texture,'UnityEngine.Texture2D')
   natives.append(_pointer(r.u64(texture+16),'native texture',nullable=True))
  else:natives.append(0)
 controller=_pointer(r.u64(a+fs['<TransitionController>k__BackingField']),'transition controller')
 state=struct.unpack('<i',r.read(controller+20,4))[0]
 material=_pointer(r.u64(data+df['SharedMaterial']),'material',nullable=True)
 native_material=_pointer(r.u64(material+16),'native material',nullable=True) if material else 0
 active_result=_pointer(r.u64(a+fs['<Result>k__BackingField']),'active result',nullable=True)
 return {'address':hex(a),'data':hex(data),'region_count':count,'native_textures':[hex(x) for x in natives],'live_textures':all(natives),'native_material':hex(native_material),'controller_state':state,'active_result':hex(active_result),'capture_eligible':all(natives) and bool(native_material) and bool(active_result) and state==2}
def scan(r,capture=False,*,adapter=None):
 if adapter is None:
  import hashlib
  from .build_layout import resolve_build_files
  from .build_adapters import select_adapter
  files=resolve_build_files(r.module_files)
  adapter=select_adapter({name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in files.items()})
 cls=r.u64(r.base+adapter.palette_class_rva);hits=[];saved=[];seen=set();total=0;t=time.perf_counter()
 if cls in (0,adapter.palette_uninitialized_marker):return hits,saved,total,time.perf_counter()-t
 _pointer(cls,'dye class',class_pointer=True)
 if r.class_name(cls)!='MM.Client.Presentation.UI.Instances.StageScene.Dyeing.DyeingPaletteInstanceImpl':raise ValueError('Dye class not initialized or build mismatch')
 pattern=struct.pack('<Q',cls)
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
