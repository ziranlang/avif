#!/usr/bin/env python3
"""Pinned native CfL mean/predict kernels with independent spec subsampling."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import shlex
from av1_lossless_oracle import PIN, digest, run

HOST=r'''
#include <stdio.h>
#include <stdint.h>
#include "av1/common/cfl.h"
'''
MAIN=r'''
int main(void) {
  int depth,alpha;unsigned dc;
  while(scanf("%d%d%u",&depth,&alpha,&dc)==3) {
    if((depth!=8&&depth!=10&&depth!=12)||alpha<-16||alpha>16||dc>=(1u<<depth))return 1;
    uint16_t q3[CFL_BUF_LINE*CFL_BUF_LINE]={0},output[28];int16_t ac[CFL_BUF_LINE*CFL_BUF_LINE]={0};
    for(int y=0;y<4;y++)for(int x=0;x<4;x++) {
      unsigned value;if(scanf("%u",&value)!=1||value>((1u<<depth)-1)*8)return 2;q3[y*CFL_BUF_LINE+x]=value;
    }
    subtract_average_c(q3,ac,4,4,8,4);
    for(int y=0;y<4;y++)for(int x=0;x<7;x++)output[y*7+x]=x<4?dc:65535;
    cfl_predict_hbd_c(ac,output,7,alpha,depth,4,4);
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
    upstream=(a.aom/'av1/common/cfl.c').read_text();native=''
    for name in ('static void subtract_average_c(', 'static inline void cfl_predict_hbd_c('):
        start=upstream.index(name);end=upstream.index('\n}\n',start)+3;native+=upstream[start:end]
    source=a.out/'oracle.c';source.write_text(HOST+native+MAIN);host=a.out/'oracle'
    config=Path(os.environ.get('AV1_AOM_CONFIG',str(a.root/'build/native/aom')))
    library=Path(os.environ.get('AV1_AOM_LIBRARY',str(a.root/'build/external/lib/libaom.a')))
    run(shlex.split(os.environ.get('CC','cc'))+['-std=c11','-O2','-I'+str(a.aom),'-I'+str(config),str(source),str(library),'-lm','-o',str(host)])
    rng=random.Random(0x41563143464c3434);cases=[]
    for depth in (8,10,12):
        maximum=(1<<depth)-1
        for alpha in range(-16,17):
            for sx,sy in ((0,0),(1,0),(1,1)):
                scenarios=[(8,8,0,0),(8,8,3,3),(8,8,7,7),(8,8,1,2),(4,4,0,0),(1+sx,1+sy,0,0)]
                for index,(width,height,start_x,start_y) in enumerate(scenarios):
                    samples=[rng.randrange(maximum+1) for _ in range(64)]
                    if index==0:samples=[0,maximum]*32
                    dc=rng.randrange(maximum+1);q3=[]
                    for y in range(4):
                        ly=min((start_y+y)*(1+sy),height-(1+sy))
                        for x in range(4):
                            lx=min((start_x+x)*(1+sx),width-(1+sx))
                            value=sum(samples[(ly+dy)*8+lx+dx] for dy in range(sy+1) for dx in range(sx+1))
                            q3.append(value<<(3-sx-sy))
                    cases.append(dict(depth=depth,alpha=alpha,sx=sx,sy=sy,width=width,height=height,start_x=start_x,start_y=start_y,dc=dc,luma=samples,q3=q3))
    text=''.join(' '.join(map(str,[c['depth'],c['alpha'],c['dc']]+c['q3']))+'\n' for c in cases)
    outputs=run([str(host)],input=text,text=True,capture_output=True).stdout.splitlines()
    if len(outputs)!=len(cases):raise SystemExit('native CfL vector count mismatch')
    module=os.path.relpath(a.root/'src/av1/cfl.zi',a.out);bounds=os.path.relpath(a.root/'tests/av1_cfl.zi',a.out)
    lines=['#import, file "'+module+'";','#import, file "'+bounds+'";','using Codec :: #import "image_codec/api"',
        '#program_export','main :: () -> s32 {','    if CflBoundaries() != 0 { return 99 }']
    for group in range((len(cases)+15)//16):lines.append(f'    if Group{group}() != 0 {{ return {group+1} }}')
    lines+=['    return 0','}']
    for group in range((len(cases)+15)//16):
        lines.append(f'Group{group} :: () -> s32 {{')
        for i in range(group*16,min(group*16+16,len(cases))):
            c=cases[i];expected=list(map(int,outputs[i].split()))
            if len(expected)!=16:raise SystemExit('native CfL output width mismatch')
            lines+=['    {','        luma: [64]u16 = .['+','.join(map(str,c['luma']))+']',
                f'        result := PredictCfl4x4(luma[:], 8, {c["width"]}, {c["height"]}, {c["start_x"]}, {c["start_y"]}, {c["sx"]}, {c["sy"]}, {c["dc"]}, {c["alpha"]}, {c["depth"]})',
                '        expected: [16]u16 = .['+','.join(map(str,expected))+']',
                '        if result.error.code != DecodeOK { return 1 }',
                '        for j: 0..15 { if result.samples[j] != expected[j] { return 2 } }','    }']
        lines+=['    return 0','}']
    (a.out/'av1_cfl_vectors.zi').write_text('\n'.join(lines)+'\n')
    (a.out/'oracle.json').write_text(json.dumps(dict(revision=PIN,library_sha256=digest(library),native_scalar_sha256=hashlib.sha256(native.encode()).hexdigest(),
        vectors=len(cases),depths=[8,10,12],alphas=list(range(-16,17)),subsampling=['444','422','420'],edge_scenarios=6,
        scope='standalone4x4 scalar CfL subsampling/mean/prediction; color decoder integration pending'),indent=2)+'\n')
    print(f'Pinned scalar CfL oracle: {len(cases)} vectors; alpha-16..16,444/422/420,8/10/12-bit and clamped edges')


if __name__=='__main__':main()
