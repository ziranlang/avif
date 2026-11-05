#!/usr/bin/env python3
"""Actual pinned directional scalar kernels and standard whole-frame vectors."""
import argparse
import json
import os
from pathlib import Path
import random
import re
import shlex
from av1_coefficient_edges import HOST as ENCODER
from av1_filter_intra_oracle import cdfs, rectangles
from av1_lossless_oracle import PIN, digest, run
from av1_still_oracle import HOST as DECODER
from av1_frame_oracle import zi_bytes

SCALAR = r'''
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "av1/common/reconintra.h"
void av1_highbd_filter_intra_edge_c(uint16_t*,int,int);
void av1_highbd_upsample_intra_edge_c(uint16_t*,int,int);
void av1_highbd_dr_prediction_z1_c(uint16_t*,ptrdiff_t,int,int,const uint16_t*,const uint16_t*,int,int,int,int);
void av1_highbd_dr_prediction_z2_c(uint16_t*,ptrdiff_t,int,int,const uint16_t*,const uint16_t*,int,int,int,int,int);
void av1_highbd_dr_prediction_z3_c(uint16_t*,ptrdiff_t,int,int,const uint16_t*,const uint16_t*,int,int,int,int);
'''
MAIN = r'''
int main(void) {
  int depth,mode,delta,enabled,type,ha,hl;unsigned corner;
  const int angles[8]={90,180,45,135,113,157,203,67};
  while(scanf("%d%d%d%d%d%d%d%u",&depth,&mode,&delta,&enabled,&type,&ha,&hl,&corner)==8) {
    if((depth!=8&&depth!=10&&depth!=12)||mode<1||mode>8||delta<-3||delta>3||corner>=(1u<<depth))return 1;
    uint16_t a[20]={0},l[20]={0},output[28];uint16_t *above=a+2,*left=l+2;
    above[-2]=above[-1]=left[-2]=left[-1]=corner;
    for(int i=0;i<8;i++){unsigned x;if(scanf("%u",&x)!=1||x>=(1u<<depth))return 2;above[i]=x;}
    for(int i=0;i<8;i++){unsigned x;if(scanf("%u",&x)!=1||x>=(1u<<depth))return 2;left[i]=x;}
    int angle=angles[mode-1]+delta*3,ua=0,ul=0;
    if(enabled&&angle!=90&&angle!=180) {
      if(ha)av1_highbd_filter_intra_edge_c(above-1,angle<90?9:5,intra_edge_filter_strength(4,4,angle-90,type));
      if(hl)av1_highbd_filter_intra_edge_c(left-1,angle>180?9:5,intra_edge_filter_strength(4,4,angle-180,type));
      ua=av1_use_intra_edge_upsample(4,4,angle-90,type);ul=av1_use_intra_edge_upsample(4,4,angle-180,type);
      if(ua)av1_highbd_upsample_intra_edge_c(above,angle<90?8:4,depth);
      if(ul)av1_highbd_upsample_intra_edge_c(left,angle>180?8:4,depth);
    }
    for(int i=0;i<28;i++)output[i]=65535;
    if(angle<90)av1_highbd_dr_prediction_z1_c(output,7,4,4,above,left,ua,av1_get_dx(angle),1,depth);
    else if(angle<180&&angle>90)av1_highbd_dr_prediction_z2_c(output,7,4,4,above,left,ua,ul,av1_get_dx(angle),av1_get_dy(angle),depth);
    else if(angle>180)av1_highbd_dr_prediction_z3_c(output,7,4,4,above,left,ul,1,av1_get_dy(angle),depth);
    else for(int y=0;y<4;y++)for(int x=0;x<4;x++)output[y*7+x]=angle==90?above[x]:left[y];
    for(int y=0;y<4;y++) {
      for(int x=0;x<4;x++)printf("%u ",output[y*7+x]);
      for(int x=4;x<7;x++)if(output[y*7+x]!=65535)return 3;
    }printf("\n");
  }return 0;
}
'''


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--aom',type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    if run(['git','-C',str(a.aom),'rev-parse','HEAD'],text=True,capture_output=True).stdout.strip()!=PIN:raise SystemExit('libaom pin mismatch')
    run(['git','-C',str(a.aom),'diff','--quiet','HEAD','--'])
    library=Path(os.environ.get('AV1_AOM_LIBRARY',str(a.root/'build/external/lib/libaom.a')))
    config=Path(os.environ.get('AV1_AOM_CONFIG',str(a.root/'build/native/aom')))
    compiler=shlex.split(os.environ.get('CC','cc'))+['-std=c11','-O2','-I'+str(a.aom),'-I'+str(config)]
    upstream=(a.aom/'av1/common/reconintra.c').read_text()
    start=upstream.index('static int intra_edge_filter_strength(');end=upstream.index('\n}\n',start)+3
    scalar_source=a.out/'scalar.c';scalar_source.write_text(SCALAR+upstream[start:end]+MAIN)
    scalar=a.out/'scalar';run(compiler+[str(scalar_source),str(library),'-lm','-o',str(scalar)])
    header=(a.aom/'av1/common/reconintra.h').read_text()
    text=header.split('dr_intra_derivative[90] = {',1)[1].split('};',1)[0]
    values=list(map(int,re.findall(r'\d+',re.sub(r'//[^\n]*','',text))))
    product=(a.root/'src/av1/directional.zi').read_text()
    angles=list(map(int,re.search(r'angles: \[27\]s32 = \.\[([^]]+)\]',product)[1].split(',')))
    slopes=list(map(int,re.search(r'slopes: \[27\]s32 = \.\[([^]]+)\]',product)[1].split(',')))
    if len(values)!=90 or list(zip(angles,slopes))!=[(i,v) for i,v in enumerate(values) if v]:raise SystemExit('derivative provenance mismatch')
    rng=random.Random(0x4156314449524543);scalar_cases=[]
    for depth in (8,10,12):
        maximum=(1<<depth)-1;middle=1<<(depth-1)
        for mode in range(1,9):
            for delta in range(-3,4):
                for enabled in (False,True):
                    for kind in (0,1):
                        for variant in (0,1):
                            flags=(len(scalar_cases)//2+variant*2)%4;ha=bool(flags&1);hl=bool(flags&2)
                            above=[rng.randrange(maximum+1) for _ in range(8)];left=[rng.randrange(maximum+1) for _ in range(8)]
                            corner=rng.randrange(maximum+1)
                            if variant==0:above=[0,maximum]*4;left=[maximum,0]*4;corner=maximum
                            if not ha:above=[left[0] if hl else middle-1]*8
                            if not hl:left=[above[0] if ha else middle+1]*8
                            if not ha or not hl:corner=above[0] if ha else (left[0] if hl else middle)
                            scalar_cases.append(dict(depth=depth,mode=mode,delta=delta,enabled=enabled,kind=kind,ha=ha,hl=hl,corner=corner,above=above,left=left))
    stream=''.join(' '.join(map(str,[c['depth'],c['mode'],c['delta'],int(c['enabled']),c['kind'],int(c['ha']),int(c['hl']),c['corner']]+c['above']+c['left']))+'\n' for c in scalar_cases)
    scalar_outputs=run([str(scalar)],input=stream,text=True,capture_output=True).stdout.splitlines()
    if len(scalar_outputs)!=len(scalar_cases):raise SystemExit('native directional count mismatch')
    source=a.out/'decoder.c';source.write_text(DECODER.replace(
        'bad_mode+=!supported;','bad_mode+=mode<DC_PRED||mode>PAETH_PRED;'))
    decoder=a.out/'decoder';run(compiler+[str(source),str(library),'-Wl,--wrap=av1_read_mode_info','-lm','-o',str(decoder)])
    source=a.out/'encoder.c';source.write_text(ENCODER.replace('count>32','count>128').replace('cdf[32][17]','cdf[128][17]').replace('n[32]','n[128]'))
    encoder=a.out/'encoder';run(compiler+[str(source),str(a.aom/'aom_dsp/entenc.c'),str(library),'-lm','-o',str(encoder)])
    entropy=(a.aom/'av1/common/entropymode.c').read_text()
    tables=cdfs(entropy,'default_partition_cdf',4,4)+cdfs(entropy,'default_partition_cdf',12,10)
    tables += [[31671,32768],[16515,32768],[4576,32768]]
    keyframe=len(tables);tables+=cdfs(entropy,'default_kf_y_mode_cdf',25,13)
    angle_table=len(tables);tables+=cdfs(entropy,'default_angle_delta_cdf',8,7)
    def encode(operations):
        text=str(len(tables))+'\n'+''.join(str(len(row))+' '+' '.join(map(str,row))+'\n' for row in tables)
        text+=str(len(operations))+'\n'+''.join(f'{table} {symbol} 1\n' for table,symbol in operations)
        result=list(map(int,run([str(encoder)],input=text,text=True,capture_output=True).stdout.split()))
        if result[0]!=len(result)-1:raise SystemExit('native entropy length mismatch')
        return bytes(result[1:])
    cases=[];commands=[];contexts=[0,1,2,3,4,4,4,4,3,0,1,2,0]
    for depth in (8,10,12):
        for enabled in (False,True):
            raw=a.out/f'{depth}-{int(enabled)}.gray';raw.write_bytes(((1<<(depth-1))+2).to_bytes(1 if depth==8 else 2,'little')*256)
            obu=raw.with_suffix('.obu')
            command=['ffmpeg','-hide_banner','-loglevel','error','-f','rawvideo','-pixel_format','gray' if depth==8 else f'gray{depth}le',
                '-video_size','16x16','-framerate','1','-i',str(raw),'-frames:v','1','-c:v','libaom-av1','-threads','1','-row-mt','0',
                '-cpu-used','8','-crf','0','-b:v','0','-still-picture','1','-aom-params',
                f'enable-intrabc=0:enable-palette=0:enable-filter-intra=0:enable-intra-edge-filter={int(enabled)}:enable-restoration=0:enable-cdef=0','-f','obu','-y',str(obu)]
            run(command);commands.append(command);template=obu.read_bytes();at=0
            while at<len(template):
                start=at;header=template[at];at+=1
                if header&4:at+=1
                length=shift=0
                while True:
                    byte=template[at];at+=1;length|=(byte&127)<<shift;shift+=7
                    if not byte&128:break
                if header>>3&15==6:break
                at+=length
            if template[at:at+2]!=bytes([16,0]):raise SystemExit('native frame template changed')
            for mode in range(1,9):
                for delta in range(-3,4):
                    part=(mode*7+delta+3)%10;operations=[(4,part)];skips=[[0]*4 for _ in range(4)];modes=[[0]*4 for _ in range(4)]
                    blocks=rectangles(part)
                    for row,column,width,height in blocks:
                        if part==3:operations.append((0,0))
                        r=row//4;c=column//4
                        context=(skips[r-1][c] if r else 0)+(skips[r][c-1] if c else 0)
                        above=contexts[modes[r-1][c]] if r else 0;left=contexts[modes[r][c-1]] if c else 0
                        operations += [(16+context,1),(keyframe+above*5+left,mode),(angle_table+mode-1,delta+3)]
                        for y in range(r,r+height//4):
                            for x in range(c,c+width//4):skips[y][x]=1;modes[y][x]=mode
                    tile=encode(operations)
                    if len(tile)+2>=128:raise SystemExit('fixture one-byte length exceeded')
                    data=template[:start]+bytes([header,len(tile)+2])+template[at:at+2]+tile
                    path=a.out/f'frame-{depth}-{int(enabled)}-{mode}-{delta}.obu';path.write_bytes(data)
                    output=run([str(decoder),str(path)],text=True,capture_output=True).stdout.splitlines()
                    values=list(map(int,output[0].split()));count,bad,rects=map(int,output[1].split())
                    if values[:2]!=[16,depth] or len(values)!=258 or count!=len(blocks) or bad:raise SystemExit('native directional frame rejected')
                    cases.append(dict(depth=depth,mode=mode,delta=delta,enabled=enabled,part=part,data=list(data),samples=values[2:]))
    rel=os.path.relpath(a.root/'src/av1/directional.zi',a.out);bounds=os.path.relpath(a.root/'tests/av1_directional.zi',a.out)
    decoder_rel=os.path.relpath(a.root/'src/av1/decoder.zi',a.out)
    lines=['#import, file "'+rel+'";','#import, file "'+bounds+'";','#import, file "'+decoder_rel+'";',
        'using Codec :: #import "image_codec/api"','#program_export','main :: () -> s32 {','    if DirectionalBoundaries() != 0 { return 99 }']
    for i in range((len(scalar_cases)+15)//16):lines.append(f'    if Scalar{i}() != 0 {{ return {i+1} }}')
    for i in range(len(cases)):lines.append(f'    if Frame{i}() != 0 {{ return {i%250+1} }}')
    lines+=['    return 0','}']
    for group in range((len(scalar_cases)+15)//16):
        lines.append(f'Scalar{group} :: () -> s32 {{')
        for i in range(group*16,min(group*16+16,len(scalar_cases))):
            c=scalar_cases[i];expected=list(map(int,scalar_outputs[i].split()))
            if len(expected)!=16:raise SystemExit('native scalar output length')
            lines+=['    {','        above: [8]u16 = .['+','.join(map(str,c['above']))+']',
                '        left: [8]u16 = .['+','.join(map(str,c['left']))+']',
                f'        result := PredictDirectional4x4(above[:], left[:], {c["corner"]}, {str(c["ha"]).lower()}, {str(c["hl"]).lower()}, {c["mode"]}, {c["delta"]}, {str(c["enabled"]).lower()}, {c["kind"]}, {c["depth"]})',
                '        expected: [16]u16 = .['+','.join(map(str,expected))+']',
                '        if result.error.code != DecodeOK { return 1 }',
                '        for j: 0..15 { if result.samples[j] != expected[j] { return 2 } }','    }']
        lines+=['    return 0','}']
    for i,c in enumerate(cases):
        data,_=zi_bytes('bytes',c['data'],f'Directional{i}')
        lines+=[f'Frame{i} :: () -> s32 {{',data.rstrip(),'    options := DefaultOptions()',
            '    budget := NewWorkerBudget(options.limits); options.workers = *budget',
            '    image := DecodeAv1YUV(BorrowBytes(bytes[:]), *options)',
            f'    if !image.is_ok || image.sequence.enable_intra_edge_filter != {str(c["enabled"]).lower()} {{ return 1 }}',
            '    expected: [256]u16 = .['+','.join(map(str,c['samples']))+']',
            '    for pixel: 0..255 {','        value := cast(u32)image.y.storage[pixel * image.y.sample_bytes]',
            '        if image.y.sample_bytes == 2 { value |= cast(u32)image.y.storage[pixel * 2 + 1] << 8 }',
            '        if value != expected[pixel] { return 2 }','    }',
            '    if budget.active_workers != 0 || budget.working_bytes != 0 { return 3 }','    return 0','}']
    (a.out/'av1_directional_vectors.zi').write_text('\n'.join(lines)+'\n')
    (a.out/'oracle.json').write_text(json.dumps(dict(revision=PIN,library_sha256=digest(library),scalar_vectors=len(scalar_cases),
        native_whole_frames=len(cases),depths=[8,10,12],directional_modes=list(range(1,9)),angle_deltas=list(range(-3,4)),
        filter_types=[0,1],edge_filter_enabled=[False,True],partition_types=list(range(10)),commands=commands,
        scope='fixed4x4 directional kernels and standard whole-frame syntax; broader AV1 pending'),indent=2)+'\n')
    print(f'Pinned directional oracle: {len(scalar_cases)} scalar vectors, {len(cases)} native whole frames;8 modes x7 deltas, edge filter/upsampling,8/10/12-bit')


if __name__=='__main__':main()
