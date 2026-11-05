"""Turn the pinned C oracle's small synthetic planes into portable test data."""
from pathlib import Path
import sys

source, destination = map(Path,sys.argv[1:])
lines = source.read_text().splitlines()
assert len(lines)%6==0
rows=[]
for at in range(0,len(lines),6):
    values=list(map(int,lines[at].split()))
    buffers=[bytes.fromhex(line) for line in lines[at+1:at+6]]
    assert len(values)==8 and all(len(v)<=96 for v in buffers[:4]) and len(buffers[4])==140
    rows.append((values,buffers))
declarations=["""ColorCase :: struct {
    depth: s32; full: s32; matrix: s32; sx: s32; sy: s32; mono: s32; alpha_mode: s32; filter: s32
    y: [96]u8; u: [96]u8; v: [96]u8; alpha: [96]u8; expected: [140]u8
}
"""]
for index,(values,buffers) in enumerate(rows):
    declarations.append(f'Case_{index} :: () -> ColorCase {{\n    result: ColorCase\n')
    for name,value in zip(['depth','full','matrix','sx','sy','mono','alpha_mode','filter'],values):
        declarations.append(f'    result.{name} = {value}\n')
    for i,(name,data) in enumerate(zip(['y','u','v','alpha','expected'],buffers)):
        padded=list(data)+[0]*((96 if i<4 else 140)-len(data))
        declarations.append(f'    {name}: [{len(padded)}]u8 = .['+','.join(map(str,padded))+']\n')
        declarations.append(f'    result.{name} = {name}\n')
    declarations.append('    return result\n}\n')
declarations.append(f'COLOR_CASE_COUNT :: {len(rows)};\nGetColorCase :: (index: s64) -> ColorCase {{\n')
for index in range(len(rows)):
    declarations.append(f'    if index == {index} {{ return Case_{index}() }}\n')
declarations.append('    empty: ColorCase; return empty\n}\n')
destination.write_text(''.join(declarations))
print(f'Pinned libavif1.3 synthetic plane oracle: {len(rows)} color/range/depth/sampling/alpha cases')
