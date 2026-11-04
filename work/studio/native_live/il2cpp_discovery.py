"""Bounded, cancellable offline IL2CPP v31/x64 discovery.

Only reads client files. The metadata table format follows the IL2CPP v31
layout; unsupported versions and ambiguous registrations are rejected.
"""
import bisect, struct, hashlib
from pathlib import Path
import capstone, pefile

def read_build_file(path, expected, limit, check):
    check();path=Path(path);before=path.stat()
    if not 0<before.st_size<=limit:raise ValueError('Unsupported metadata/build file size')
    chunks=[];digest=hashlib.sha256();total=0
    with path.open('rb') as stream:
        while True:
            check();chunk=stream.read(1024*1024)
            if not chunk:break
            total+=len(chunk)
            if total>limit or total>before.st_size:raise ValueError('Game build changed during adaptive discovery')
            chunks.append(chunk);digest.update(chunk)
    after=path.stat();check()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns) or digest.hexdigest()!=expected:
        raise ValueError('Game build changed during adaptive discovery')
    return b''.join(chunks)


class Build:
    def __init__(self, files, hashes, check=lambda:None):
        self.check=check
        self.m=read_build_file(files['metadata'],hashes['metadata'],256*1024**2,check)
        if len(self.m)<176 or struct.unpack_from('<II',self.m)!=(0xfab11baf,31):
            raise ValueError('Unsupported metadata schema (adaptive discovery requires v31)')
        self.d=read_build_file(files['gameassembly'],hashes['gameassembly'],1024**3,check)
        self.pe=pefile.PE(data=self.d,fast_load=True)
        try:
            self._initialize()
        except BaseException:
            self.pe.close()
            raise

    def _initialize(self):
        check=self.check
        if self.pe.FILE_HEADER.Machine!=0x8664 or self.pe.OPTIONAL_HEADER.Magic!=0x20b:
            raise ValueError('Unsupported game build architecture')
        self.base=self.pe.OPTIONAL_HEADER.ImageBase
        self.so,self.sn=self.pair(24);self.mo,self.mn=self.pair(48)
        self.fo,self.fn=self.pair(96);self.to,self.tn=self.pair(160);self.po,self.pn=self.pair(88)
        self.io,self.ins=self.pair(168)
        self.images=[];self.mods={};self.types=[];self.method_starts=[]
        for offset,size,stride in ((self.io,self.ins,40),(self.to,self.tn,88),(self.mo,self.mn,36),
                                   (self.fo,self.fn,12),(self.po,self.pn,12)):
            if size%stride or size//stride>1000000:raise ValueError('Invalid metadata table size')
        for i in range(self.ins//40):
            check()
            ni,ai,start,count=struct.unpack_from('<IiII',self.m,self.io+i*40)
            if start+count>self.tn//88:raise ValueError('Invalid metadata image range')
            self.images.append((self.st(ni),start,count))
        for i in range(self.tn//88):
            if i%1024==0:check()
            v=struct.unpack_from('<16i8H2I',self.m,self.to+i*88)
            for start,count,total in ((v[8],v[18],self.fn//12),(v[9],v[16],self.mn//36)):
                if count and (start<0 or start+count>total):raise ValueError('Invalid metadata type range')
            self.types.append((v,self.st(v[1])+'.'+self.st(v[0])))
        dd=self.pe.OPTIONAL_HEADER.DATA_DIRECTORY[3];o=self.off(self.base+dd.VirtualAddress)
        if dd.Size%12 or dd.Size>len(self.d)-o:raise ValueError('Invalid game build unwind table')
        self.funcs=list(struct.iter_unpack('<III',self.d[o:o+dd.Size]));self.starts=[f[0] for f in self.funcs]
        if self.starts!=sorted(self.starts):raise ValueError('Unordered game build unwind table')
        self.md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);self.md.detail=True
        self.field_table=self.discover_field_table()
    def pair(self,a):
        offset,size=struct.unpack_from('<II',self.m,a)
        if offset>len(self.m) or size>len(self.m)-offset:raise ValueError('Invalid metadata table bounds')
        return offset,size
    def st(self,i):
        if not 0<=i<self.sn:raise ValueError('Invalid metadata string index')
        end=self.m.find(b'\0',self.so+i,self.so+self.sn)
        if end<0:raise ValueError('Unterminated metadata string')
        return self.m[self.so+i:end].decode('utf8')
    def off(self,va):
        self.check()
        rva=va-self.base;section=self.pe.get_section_by_rva(rva)
        if section is None or not 0<=rva-section.VirtualAddress<section.SizeOfRawData:
            raise ValueError('Unmapped game build address')
        offset=section.PointerToRawData+rva-section.VirtualAddress
        if not 0<=offset<len(self.d):raise ValueError('Invalid PE file offset')
        return offset
    def read(self,va,size):
        offset=self.off(va);section=self.pe.get_section_by_rva(va-self.base)
        delta=va-self.base-section.VirtualAddress
        if size<0 or size>section.SizeOfRawData-delta or size>len(self.d)-offset:
            raise ValueError('Truncated game build data')
        return self.d[offset:offset+size]
    def u64(self,va):return struct.unpack('<Q',self.read(va,8))[0]
    def module(self,name):
        if name in self.mods:return self.mods[name]
        needle=name.encode()+b'\0';pos=0;candidates=[]
        while True:
            self.check()
            pos=self.d.find(needle,pos)
            if pos<0:break
            va=self.base+self.pe.get_rva_from_offset(pos);at=0
            while True:
                self.check()
                at=self.d.find(struct.pack('<Q',va),at)
                if at<0:break
                if at%8==0:
                    n,ptr=struct.unpack_from('<QQ',self.d,at+8)
                    if 0<n<1000000 and self.base<ptr<self.base+self.pe.OPTIONAL_HEADER.SizeOfImage:
                        candidates.append((self.base+self.pe.get_rva_from_offset(at),n,ptr))
                at+=1
            pos+=1
        if len(candidates)!=1:raise ValueError((name,'Ambiguous module',candidates))
        self.mods[name]=candidates[0]
        _,n,ptr=candidates[0];o=self.off(ptr)
        if n*8>len(self.d)-o:raise ValueError('Invalid game build method pointer table')
        self.method_starts=sorted(set(self.method_starts)|{x[0] for x in struct.iter_unpack('<Q',self.read(ptr,n*8)) if x[0]})
        return candidates[0]
    def image(self,ti):
        images=[name for name,start,count in self.images if start<=ti<start+count]
        if len(images)!=1:raise ValueError('Ambiguous metadata type image')
        return images[0]
    def fields(self,v):
        result=[]
        for i in range(v[8],v[8]+v[18]):
            ni,typ,token=struct.unpack_from('<iiI',self.m,self.fo+i*12)
            result.append(dict(name=self.st(ni),type_index=typ,token=hex(token)))
        return result
    def discover_field_table(self):
        needle=struct.pack('<Q',len(self.types));at=0;candidates=[]
        while True:
            self.check()
            at=self.d.find(needle,at)
            if at<0:break
            if at%8==0 and self.d[at+16:at+24]==needle:
                fields,sizes=struct.unpack_from('<Q',self.d,at+8)[0],struct.unpack_from('<Q',self.d,at+24)[0]
                try:
                    self.off(fields);self.off(sizes)
                    if all(self.u64(fields+i*8)==0 or self.base<=self.u64(fields+i*8)<self.base+self.pe.OPTIONAL_HEADER.SizeOfImage for i in range(16)):
                        count,table=struct.unpack_from('<QQ',self.d,at-32)
                        if 0<count<1000000 and self.base<=table<self.base+self.pe.OPTIONAL_HEADER.SizeOfImage:
                            candidates.append((fields,count,table))
                except (ValueError,struct.error,pefile.PEFormatError):pass
            at+=1
        if len(candidates)!=1:raise ValueError(('Ambiguous field-offset registration',candidates))
        fields,self.type_count,self.type_table=candidates[0]
        return fields
    def type_name(self,index):
        if index<0:return None
        if not index<self.type_count:raise ValueError('Invalid Il2CppType index')
        return self.type_pointer_name(self.u64(self.type_table+index*8))
    def type_pointer_name(self,ptr,depth=0):
        if depth>32:raise ValueError("Recursive metadata type")
        data,bits=struct.unpack('<QI',self.read(ptr,12));kind=(bits>>16)&255
        simple={1:'void',2:'bool',3:'char',4:'int8',5:'uint8',6:'int16',7:'uint16',8:'int32',9:'uint32',10:'int64',11:'uint64',12:'float32',13:'float64',14:'string',22:'TypedReference',24:'IntPtr',25:'UIntPtr',28:'object'}
        if kind in simple:name=simple[kind]
        elif kind in (17,18):
            if data>=len(self.types):raise ValueError('Invalid metadata type definition')
            name=self.types[data][1]
        elif kind in (15,16,29):name=self.type_pointer_name(data,depth+1)+{15:'*',16:'&',29:'[]'}[kind]
        elif kind==21:
            typ=self.u64(data);inst=self.u64(data+8);count=self.u64(inst);argv=self.u64(inst+8)
            if count>32:raise ValueError('Invalid generic argument count')
            name=self.type_pointer_name(typ,depth+1)+'<'+','.join(self.type_pointer_name(self.u64(argv+i*8),depth+1) for i in range(count))+'>'
        elif kind in (19,30):
            gp,gn=self.pair(104)
            if gn%16 or data>=gn//16:raise ValueError('Invalid generic metadata parameter')
            number=struct.unpack_from('<H',self.m,gp+data*16+12)[0]
            name=('T' if kind==19 else 'M')+str(number)
        elif kind==20:
            element=self.u64(data);rank=self.d[self.off(data)+8]
            if not 1<=rank<=32:raise ValueError('Invalid metadata array rank')
            name=self.type_pointer_name(element,depth+1)+'['+','*(rank-1)+']'
        else:raise ValueError(('Unknown Il2CppType kind',kind))
        if bits&(1<<29):name+='&'
        return name
    def field_offsets(self,ti):
        v,_=self.types[ti];fields=self.fields(v);ptr=self.u64(self.field_table+ti*8)
        if not fields:return fields
        if not ptr:raise ValueError('No offsets for fields')
        for i,f in enumerate(fields):
            f['offset']=struct.unpack('<i',self.read(ptr+i*4,4))[0]
            f['type_name']=self.type_name(f['type_index'])
        return fields
    def methods(self,ti,v):
        _,n,ptr=self.module(self.image(ti));result=[]
        for i in range(v[9],v[9]+v[16]):
            q=struct.unpack_from('<6iI4H',self.m,self.mo+i*36);idx=(q[6]&0xffffff)-1
            va=self.u64(ptr+idx*8) if 0<=idx<n else 0
            params=[]
            if q[10] and (q[4]<0 or q[4]+q[10]>self.pn//12):raise ValueError('Invalid method parameter range')
            for pi in range(q[4],q[4]+q[10]):
                ni,tk,typ=struct.unpack_from('<iIi',self.m,self.po+pi*12)
                params.append(self.type_name(typ))
            result.append(dict(name=self.st(q[0]),parameters=params,return_type=self.type_name(q[2]),token=hex(q[6]),rva=hex(va-self.base) if va else None))
        return result
    def instructions(self,rva):
        va=self.base+int(rva,16);idx=bisect.bisect_right(self.starts,va-self.base)-1
        section=self.pe.get_section_by_rva(va-self.base)
        if section is None or not section.Characteristics&0x20000000:
            raise ValueError('Metadata method points outside executable code')
        nxt=bisect.bisect_right(self.method_starts,va)
        end=self.method_starts[nxt] if nxt<len(self.method_starts) else va+512
        if idx>=0 and self.funcs[idx][0]<=va-self.base<self.funcs[idx][1]:end=min(end,self.base+self.funcs[idx][1])
        size=min(end-va,50000,section.SizeOfRawData-(va-self.base-section.VirtualAddress))
        if size<=0:raise ValueError('Empty game build method')
        result=[]
        for ins in self.md.disasm(self.read(va,size),va):
            self.check()
            if ins.mnemonic=='int3':break
            result.append(ins)
        return result
