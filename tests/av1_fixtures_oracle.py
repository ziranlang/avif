#!/usr/bin/env python3
"""Authored AV1 decode of the real AVIF fixtures, through the avif container.

Test-only native code: pinned libaom decodes each fixture's color and alpha
AV1 item bytes and reports per-row hashes. The generated Ziran program parses
the same .avif with avif's ParseAvif/ExtractItem, decodes each item with the
av1 package's DecodeAv1YUV and must match every row bit-exactly.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess

PIN='d772e334cc724105040382a977ebb10dfd393293'
NAMES=['rgba8','rgba10','rgba12','gray8','gray10','gray12','transform00','transform01','transform10','transform11',
    'transform20','transform21','transform30','transform31','premultiplied','opaque','animated']
HOST=r'''
#include <stdio.h>
#include <stdint.h>
#include "aom/aom_decoder.h"
#include "aom/aomdx.h"
int main(int argc,char **argv) {
  if(argc!=2)return 1;FILE *f=fopen(argv[1],"rb");if(!f)return 2;
  static unsigned char data[1<<20];size_t bytes=fread(data,1,sizeof(data),f);fclose(f);if(!bytes||bytes==sizeof(data))return 3;
  aom_codec_ctx_t codec={0};aom_codec_dec_cfg_t cfg={0};cfg.threads=1;cfg.allow_lowbitdepth=1;
  if(aom_codec_dec_init(&codec,aom_codec_av1_dx(),&cfg,0))return 4;
  if(aom_codec_decode(&codec,data,bytes,NULL)){fprintf(stderr,"native decode: %s\n",aom_codec_error(&codec));return 5;}
  aom_codec_iter_t it=NULL;aom_image_t *image=aom_codec_get_frame(&codec,&it);if(!image)return 6;
  printf("%u %u %u %d %u %u\n",image->d_w,image->d_h,image->bit_depth,image->monochrome,image->x_chroma_shift,image->y_chroma_shift);
  for(int plane=0;plane<3;plane++) {
    if(image->monochrome&&plane){printf("\n");continue;}
    unsigned sx=plane?image->x_chroma_shift:0,sy=plane?image->y_chroma_shift:0;
    unsigned width=(image->d_w+((1u<<sx)-1))>>sx,height=(image->d_h+((1u<<sy)-1))>>sy;
    for(unsigned y=0;y<height;y++) {
      long long hash=0;
      for(unsigned x=0;x<width;x++) {
        unsigned value=image->fmt&AOM_IMG_FMT_HIGHBITDEPTH?((uint16_t*)(image->planes[plane]+y*image->stride[plane]))[x]:image->planes[plane][y*image->stride[plane]+x];
        hash=(hash*131+(value&255)+1)%2147483629LL;
        if(image->bit_depth>8)hash=(hash*131+(value>>8)+1)%2147483629LL;
      }
      printf("%lld ",hash);
    }
    printf("\n");
  }
  return aom_codec_destroy(&codec);
}
'''


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def native_rows(decoder,path):
    lines=subprocess.run([str(decoder),str(path)],check=True,text=True,capture_output=True).stdout.split('\n')
    w,h,depth,mono,sx,sy=map(int,lines[0].split())
    return dict(width=w,height=h,depth=depth,mono=mono,sx=sx,sy=sy,rows=[list(map(int,lines[1+p].split())) for p in range(3)])


def literal(name,data):
    rows=[','.join(map(str,data[i:i+64])) for i in range(0,len(data),64)]
    return f'    {name}: [{len(data)}]u8 = .[\n        '+',\n        '.join(rows)+'\n    ]'


def main():
    p=argparse.ArgumentParser()
    for name in ('root','av1','out','aom','library'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    if subprocess.run(['git','-C',str(a.aom),'rev-parse','HEAD'],check=True,text=True,capture_output=True).stdout.strip()!=PIN:
        raise SystemExit('libaom pin mismatch')
    subprocess.run(['git','-C',str(a.aom),'diff','--quiet','HEAD','--'],check=True)
    source=a.out/'decoder.c';source.write_text(HOST);decoder=a.out/'decoder'
    subprocess.run(shlex.split(os.environ.get('CC','cc'))+['-std=c11','-O2','-I'+str(a.aom),str(source),str(a.library),'-lm','-lpthread','-o',str(decoder)],check=True)
    fixtures=a.root/'tests/fixtures'
    manifest=json.loads((fixtures/'manifest.json').read_text())['sha256']
    cases=[]
    for name in NAMES:
        container=fixtures/f'{name}.avif'
        if manifest.get(container.name)!=digest(container):raise SystemExit(f'{container.name} differs from the pinned manifest')
        items=[]
        for part in ('color','alpha'):
            path=fixtures/f'{name}.{part}.obu'
            if not path.exists():continue
            if manifest.get(path.name)!=digest(path):raise SystemExit(f'{path.name} differs from the pinned manifest')
            items.append(dict(part=part,bytes=path.stat().st_size,native=native_rows(decoder,path)))
        cases.append(dict(name=name,data=list(container.read_bytes()),items=items))
    parse=os.path.relpath(a.root/'src/parse.zi',a.out)
    lines=['#import, file "'+parse+'";','#import "av1/decoder"','using Codec :: #import "image_codec/api"','',
        '// Row hash over owned output bytes (little-endian samples), matching the native host.',
        'CheckPlane :: (plane: *Plane, rows: []s64) -> s32 {',
        '    if plane.height != rows.count { return 1000 }',
        '    for row: 0..rows.count - 1 {',
        '        hash: s64; base := row * plane.stride',
        '        for i: 0..cast(s64)plane.width * plane.sample_bytes - 1 { hash = (hash * 131 + cast(s64)plane.storage[base + i] + 1) % 2147483629 }',
        '        if hash != rows[row] { return cast(s32)row + 1 }','    }','    return 0','}',
        '// One item through avif extraction and the authored decoder.',
        'CheckItem :: (input: BorrowedBytes, container: *AvifContainer, id: u32, count: s64, width: s32, height: s32, depth: s32,',
        '    mono: bool, sx: s32, sy: s32, y: []s64, u: []s64, v: []s64) -> s32 {',
        '    options := DefaultOptions(); budget := NewWorkerBudget(options.limits); options.workers = *budget',
        '    item := ExtractItem(input, container, id, options.limits)',
        '    if item.error.code != DecodeOK || item.data.count != count { return 1 }',
        '    data := item.data',
        '    image := DecodeAv1YUV(BorrowBytes(VecSlice(data, 0, data.count)), *options)',
        '    if !image.is_ok { return 100 + cast(s32)image.error.code }',
        '    if budget.active_workers != 0 || budget.working_bytes != 0 { return 2 }',
        '    sample: s32 = ifx depth == 8 then 1 else 2',
        '    if image.y.width != width || image.y.height != height || image.y.sample_bytes != sample || image.sequence.bit_depth != depth { return 3 }',
        '    if image.sequence.monochrome != mono || (!mono && (image.sequence.subsampling_x != sx || image.sequence.subsampling_y != sy)) { return 4 }',
        '    check := CheckPlane(*image.y, y)',
        '    if check != 0 { return 10000 + check }',
        '    if mono { return ifx image.u.storage.count == 0 && image.v.storage.count == 0 then 0 else 5 }',
        '    check = CheckPlane(*image.u, u)',
        '    if check != 0 { return 20000 + check }',
        '    check = CheckPlane(*image.v, v)',
        '    if check != 0 { return 30000 + check }',
        '    return 0','}','',
        '// Detailed result for the Go harness; C and the VM see only pass/fail.','#program_export','Run :: () -> s32 {']
    lines += [f'    result{i} := Fixture{i}()\n    if result{i} != 0 {{ return {(i+1)*1000000} + result{i} }}' for i in range(len(cases))]
    lines += ['    return 0','}','#program_export','main :: () -> s32 { return ifx Run() == 0 then 0 else 1 }','']
    items=0
    for i,c in enumerate(cases):
        lines += [f'// {c["name"]}.avif','Fixture'+str(i)+' :: () -> s32 {',literal('bytes',c['data']),
            '    input := BorrowBytes(bytes[:])','    container := ParseAvif(input, DefaultLimits())',
            '    if container.error.code != DecodeOK { return 900 }']
        for item in c['items']:
            n=item['native'];empty='empty[:0]'
            rows=[f'{item["part"]}{p}' for p in range(3)]
            for p,label in enumerate(rows):
                if n['rows'][p]:lines.append(f'    {label}: [{len(n["rows"][p])}]s64 = .['+','.join(map(str,n['rows'][p]))+']')
            args=[(f'{label}[:]' if n['rows'][p] else empty) for p,label in enumerate(rows)]
            ident='container.primary' if item['part']=='color' else 'container.alpha'
            if item['part']=='alpha':lines.append('    if container.alpha == 0 { return 901 }')
            lines += ['    empty: [1]s64' if item is c['items'][0] else '',
                f'    {item["part"]} := CheckItem(input, *container, {ident}, {item["bytes"]}, {n["width"]}, {n["height"]}, {n["depth"]}, {str(bool(n["mono"])).lower()}, {n["sx"]}, {n["sy"]}, {", ".join(args)})',
                f'    if {item["part"]} != 0 {{ return {"" if item["part"]=="color" else "200000 + "}{item["part"]} }}']
            items+=1
        if not any(item['part']=='alpha' for item in c['items']):lines.append('    if container.alpha != 0 { return 902 }')
        lines += ['    return 0','}']
    (a.out/'av1_fixtures_vectors.zi').write_text('\n'.join(line for line in lines if line!='')+'\n')
    (a.out/'oracle.json').write_text(json.dumps(dict(revision=PIN,library_sha256=digest(a.library),native_host_sha256=hashlib.sha256(HOST.encode()).hexdigest(),
        fixtures=len(cases),items=items,cases=[dict(name=c['name'],items=[dict(part=i['part'],bytes=i['bytes'],**{k:v for k,v in i['native'].items() if k!='rows'}) for i in c['items']]) for c in cases],
        scope='authored AV1 decode of the avif regression fixtures through ParseAvif/ExtractItem against pinned libaom; YUV planes only, not RGBA conversion'),indent=2)+'\n')
    print(f'AVIF fixture AV1 items: {len(cases)} containers, {items} items against pinned libaom')


if __name__=='__main__':main()
