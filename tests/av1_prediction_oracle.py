#!/usr/bin/env python3
"""Pure intra predictor reference vectors from actual pinned scalar kernels."""
import argparse
import json
import os
from pathlib import Path
import random
import shlex
from av1_lossless_oracle import PIN, digest, run

HOST=r'''
#include <stdio.h>
#include <stdint.h>
#include <stddef.h>
typedef void (*Predict)(uint16_t*,ptrdiff_t,const uint16_t*,const uint16_t*,int);
#define DECL(name) void aom_highbd_##name##_predictor_4x4_c(uint16_t*,ptrdiff_t,const uint16_t*,const uint16_t*,int)
DECL(dc);DECL(dc_left);DECL(dc_top);DECL(dc_128);DECL(v);DECL(h);DECL(smooth);DECL(smooth_v);DECL(smooth_h);DECL(paeth);
int main(void) {
  unsigned depth,mode,ha,hl,corner;
  while(scanf("%u%u%u%u%u",&depth,&mode,&ha,&hl,&corner)==5) {
    if((depth!=8&&depth!=10&&depth!=12)||mode>12||ha>1||hl>1)return 1;
    uint16_t above[5],left[4],output[28];above[0]=corner;
    for(int i=0;i<4;i++){unsigned x;if(scanf("%u",&x)!=1||x>=(1u<<depth))return 2;above[i+1]=x;}
    for(int i=0;i<4;i++){unsigned x;if(scanf("%u",&x)!=1||x>=(1u<<depth))return 2;left[i]=x;}
    Predict f=NULL;
    if(mode==0)f=ha?(hl?aom_highbd_dc_predictor_4x4_c:aom_highbd_dc_top_predictor_4x4_c):(hl?aom_highbd_dc_left_predictor_4x4_c:aom_highbd_dc_128_predictor_4x4_c);
    else if(mode==1)f=aom_highbd_v_predictor_4x4_c;
    else if(mode==2)f=aom_highbd_h_predictor_4x4_c;
    else if(mode==9)f=aom_highbd_smooth_predictor_4x4_c;
    else if(mode==10)f=aom_highbd_smooth_v_predictor_4x4_c;
    else if(mode==11)f=aom_highbd_smooth_h_predictor_4x4_c;
    else if(mode==12)f=aom_highbd_paeth_predictor_4x4_c;
    if(!f)return 3;for(int i=0;i<28;i++)output[i]=65535;
    f(output,7,above+1,left,depth);
    for(int y=0;y<4;y++){
      for(int x=0;x<4;x++)printf("%u ",output[y*7+x]);
      for(int x=4;x<7;x++)if(output[y*7+x]!=65535)return 4;
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
    source=a.out/'oracle.c';source.write_text(HOST);host=a.out/'oracle'
    library=Path(os.environ.get('AV1_AOM_LIBRARY',str(a.root/'build/external/lib/libaom.a')))
    run(shlex.split(os.environ.get('CC','cc'))+['-std=c11','-O2',str(source),str(library),'-lm','-o',str(host)])
    rng=random.Random(0x415631494e545241);cases=[]
    for depth in (8,10,12):
        maximum=(1<<depth)-1;middle=1<<(depth-1)
        for mode in (0,1,2,9,10,11,12):
            for ha in (False,True):
                for hl in (False,True):
                    for i in range(8):
                        above=[rng.randrange(maximum+1) for _ in range(4)];left=[rng.randrange(maximum+1) for _ in range(4)]
                        if i==0:above=[0,maximum,0,maximum];left=[maximum,0,maximum,0]
                        corner=rng.randrange(maximum+1)
                        if not ha:above=[left[0] if hl else middle-1]*4
                        if not hl:left=[above[0] if ha else middle+1]*4
                        if not ha or not hl:corner=above[0] if ha else (left[0] if hl else middle)
                        cases.append(dict(depth=depth,mode=mode,ha=ha,hl=hl,corner=corner,above=above,left=left))
    text=''.join(' '.join(map(str,[c['depth'],c['mode'],int(c['ha']),int(c['hl']),c['corner']]+c['above']+c['left']))+'\n' for c in cases)
    outputs=run([str(host)],input=text,text=True,capture_output=True).stdout.splitlines()
    if len(outputs)!=len(cases):raise SystemExit('native predictor case count mismatch')
    rel=os.path.relpath(a.root/'src/av1/prediction.zi',a.out)
    bounds=os.path.relpath(a.root/'tests/av1_prediction.zi',a.out)
    lines=['#import, file "'+rel+'";','#import, file "'+bounds+'";','#program_export','main :: () -> s32 {',
        '    if PredictionBoundaries() != 0 { return 99 }']
    groups=(len(cases)+15)//16
    for group in range(groups):lines.append(f'    if Group{group}() != 0 {{ return {group+1} }}')
    lines+=['    return 0','}']
    for group in range(groups):
        lines.append(f'Group{group} :: () -> s32 {{')
        for i in range(group*16,min(group*16+16,len(cases))):
            c=cases[i];expected=list(map(int,outputs[i].split()))
            lines+=['    {','        above: [4]u16 = .['+','.join(map(str,c['above']))+']',
                '        left: [4]u16 = .['+','.join(map(str,c['left']))+']',
                f'        result := PredictIntra4x4(above[:], left[:], {c["corner"]}, {str(c["ha"]).lower()}, {str(c["hl"]).lower()}, {c["mode"]}, {c["depth"]})',
                '        if result.error.code != DecodeOK { return 1 }',
                '        expected: [16]u16 = .['+','.join(map(str,expected))+']',
                '        for i: 0..15 { if result.samples[i] != expected[i] { return 2 } }','    }']
        lines+=['    return 0','}']
    (a.out/'av1_prediction_vectors.zi').write_text('\n'.join(lines)+'\n')
    (a.out/'oracle.json').write_text(json.dumps(dict(revision=PIN,library_sha256=digest(library),
        cases=len(cases),depths=[8,10,12],modes=['DC','V0','H0','Smooth','SmoothV','SmoothH','Paeth'],
        seed='0x415631494e545241',scope='4x4 scalar intra predictors; not full AV1 conformance'),indent=2)+'\n')
    print(f'Pinned scalar intra oracle: {len(cases)} edge/random vectors; DC/V/H/Smooth/Paeth at8/10/12-bit')


if __name__=='__main__':main()
