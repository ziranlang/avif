"""Explicit independent fixture pinning; never run by regression tests."""
import struct
from pathlib import Path
root = Path(__file__).resolve().parent/'fixtures'
def boxes(data, start, end):
    while start < end:
        size, kind = struct.unpack_from('>I4s', data, start)
        header = 8
        if size == 1:
            size = struct.unpack_from('>Q', data, start+8)[0]; header=16
        if size == 0: size = end-start
        assert size >= header and start+size <= end
        yield kind, start+header, start+size
        start += size
for path in sorted(root.glob('*.avif')):
    if path.stem in ('malformed','truncated','bad-crop','oversized','pixel-limit'): continue
    data=path.read_bytes()
    _, start, end = next(x for x in boxes(data,0,len(data)) if x[0] == b'meta')
    children = {kind:(a,b) for kind,a,b in boxes(data,start+4,end)}
    pitm, _ = children[b'pitm']
    version = data[pitm]; width=2 if version == 0 else 4
    primary = int.from_bytes(data[pitm+4:pitm+4+width],'big')
    at, end=children[b'iloc']; version=data[at]; at+=4
    offset_size,length_size=data[at]>>4,data[at]&15
    base_size,index_size=data[at+1]>>4,data[at+1]&15;at+=2
    def take(size):
        global at
        value=int.from_bytes(data[at:at+size],'big');at+=size;return value
    count=take(2 if version<2 else 4); items={}
    for _ in range(count):
        ident=take(2 if version<2 else 4)
        method=take(2)&15 if version else 0
        assert take(2)==0
        base=take(base_size); extents=take(2)
        out=bytearray()
        for _ in range(extents):
            if version and index_size: assert take(index_size)==0
            offset,size=take(offset_size),take(length_size)
            origin=children[b'idat'][0] if method==1 else 0
            out+=data[origin+base+offset:origin+base+offset+size]
        items[ident]=bytes(out)
    (root/(path.stem+'.color.obu')).write_bytes(items[primary])
    # Every generated non-primary item is the known alpha auxiliary image.
    others=[item for ident,item in items.items() if ident!=primary]
    if others:
        assert len(others)==1
        (root/(path.stem+'.alpha.obu')).write_bytes(others[0])
