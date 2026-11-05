"""Build bounded regression mutations in disposable package-owned outputs."""
from pathlib import Path
import struct
root=Path(__file__).resolve().parent.parent
out=root/'build/scratch/container/malformed';out.mkdir(parents=True,exist_ok=True)
data=(root/'tests/fixtures/rgba8.avif').read_bytes()
def boxes(data,start,end):
    while start<end:
        size,kind=struct.unpack_from('>I4s',data,start)
        yield kind,start,start+8,start+size
        start+=size
meta=next(b for b in boxes(data,0,len(data)) if b[0]==b'meta')
children={kind:(start,payload,end) for kind,start,payload,end in boxes(data,meta[2]+4,meta[3])}
def save(name,b): (out/(name+'.avif')).write_bytes(b)
def changed(name,at,value):
    b=bytearray(data);b[at:at+len(value)]=value;save(name,b)
pitm=children[b'pitm'];iloc=children[b'iloc'];iinf=children[b'iinf'];iprp=children[b'iprp']
changed('missing-primary',pitm[0]+4,b'free')
b=bytearray(data);b[meta[3]:meta[3]]=data[pitm[0]:pitm[2]]
struct.pack_into('>I',b,meta[1],meta[3]-meta[1]+pitm[2]-pitm[0]);save('duplicate-primary',b)
# iloc first record in these generated fixtures: v0, 4-byte offset + length.
a=iloc[1];version=data[a];assert version==0
offset_size,length_size=data[a+4]>>4,data[a+4]&15;base_size=data[a+5]>>4
record=a+8
changed('external-reference',record+2,b'\0\1')
extent_at=record+4+base_size+2
changed('extent-outside',extent_at,(len(data)+1000).to_bytes(offset_size,'big'))
# Duplicate infe IDs.
info=iinf[1];count=int.from_bytes(data[info+4:info+6],'big');assert count==2
entries=list(boxes(data,info+6,iinf[2]));first_id=data[entries[0][2]+4:entries[0][2]+6]
changed('duplicate-item',entries[1][2]+4,first_id)
props={kind:(start,payload,end) for kind,start,payload,end in boxes(data,iprp[1],iprp[2])}
ipco,ipma=props[b'ipco'],props[b'ipma']
property_boxes=list(boxes(data,ipco[1],ipco[2]))
av1c=next(b for b in property_boxes if b[0]==b'av1C')
changed('unknown-essential',av1c[1]+4,b'zzzz')
# ipma: FullBox, entry_count, item_id, association_count, properties.
a=ipma[1];assert data[a]==0 and data[a+3]==0
assoc=a+4+4+2+1
changed('bad-property-index',assoc,b'\xff')
changed('duplicate-association',assoc+1,data[assoc:assoc+1])
# Alpha auxiliary reference -> missing target.
iref=children[b'iref'];refs=list(boxes(data,iref[1]+4,iref[2]));aux=next(b for b in refs if b[0]==b'auxl')
changed('dangling-reference',aux[2]+4,b'\x7f\xff')
# Native unsupported HDR policy: container CICP transfer signals PQ or HLG.
nclx=data.index(b'nclx');changed('pq',nclx+6,b'\0\x10');changed('hlg',nclx+6,b'\0\x12')
print('Malformed container mutations prepared:',out)
