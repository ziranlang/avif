#!/usr/bin/env python3
"""Full bounded grain picture comparison to pinned av1_add_film_grain."""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
from av1_lossless_oracle import PIN, digest, run
from av1_grain_noise_oracle import GENERATOR as PARAMETERS

HOST=r'''
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "av1/decoder/grain_synthesis.h"
static unsigned sample(int index,int plane,int x,int y,int depth) {
  unsigned maximum=(1u<<depth)-1;
  if(index%4==0)return plane==0?0:plane==1?maximum:maximum/2;
  if(index%4==2){int kind=(x+y+plane)%3;return kind==0?0:kind==1?maximum:maximum/2;}
  return (x*37+y*71+plane*113+index*97+x*y*3)&maximum;
}
static void parameters(aom_film_grain_t *p,int index,int config,int lag,int depth) {
  memset(p,0,sizeof(*p));p->apply_grain=1;p->bit_depth=depth;p->ar_coeff_lag=lag;
  p->ar_coeff_shift=6+config;p->grain_scale_shift=lag;p->scaling_shift=8+lag;
  p->random_seed=index==0?0:index==47?65535:(index*997+37)&65535;
  p->num_y_points=(config==1&&lag==0)||(config==2&&lag==0)?0:config==0||config==3?14:2;
  p->chroma_scaling_from_luma=(config==1&&lag==1)||(config==3&&lag==2);
  if(config!=0&&!p->chroma_scaling_from_luma&&!(config==1&&!p->num_y_points)) {
    p->num_cb_points=10;p->num_cr_points=config==2&&lag==1?0:10;
  }
  for(int i=0;i<24;i++)p->ar_coeffs_y[i]=((i*83+index*31)&255)-128;
  for(int i=0;i<25;i++){p->ar_coeffs_cb[i]=((i*23+index*47)&255)-128;p->ar_coeffs_cr[i]=((i*67+index*13)&255)-128;}
  int *points[]={&p->scaling_points_y[0][0],&p->scaling_points_cb[0][0],&p->scaling_points_cr[0][0]};
  int counts[]={p->num_y_points,p->num_cb_points,p->num_cr_points};
  for(int plane=0;plane<3;plane++)for(int i=0;i<counts[plane];i++) {
    points[plane][i*2]=counts[plane]==1?128:i*255/(counts[plane]-1);
    points[plane][i*2+1]=(i*37+index*17+plane*13)&255;
  }
  p->cb_mult=(index*19)&255;p->cb_luma_mult=(index*73)&255;p->cb_offset=(index*91)&511;
  p->cr_mult=(index*29)&255;p->cr_luma_mult=(index*59)&255;p->cr_offset=(index*113)&511;
  p->overlap_flag=(index+config)%2;p->clip_to_restricted_range=(lag/2+config)%2;
}
int main(void) {
  int widths[]={1,7,33,64},heights[]={1,5,35,64};
  for(int index=0;index<48;index++) {
    int depth=8+2*(index/16),config=(index/4)%4,scenario=index%4;
    int w=widths[scenario],h=heights[scenario],mono=config==0,sx=config!=3,sy=config<2;
    int cw=(w+sx)/(1+sx),ch=(h+sy)/(1+sy),evenw=(w+1)&~1,evenh=(h+1)&~1;
    int identity=config==3&&scenario%2;
    aom_img_fmt_t fmt=config==3?AOM_IMG_FMT_I444:config==2?AOM_IMG_FMT_I422:AOM_IMG_FMT_I420;
    if(depth>8)fmt=(aom_img_fmt_t)(fmt|AOM_IMG_FMT_HIGHBITDEPTH);
    aom_image_t src,dst;if(!aom_img_alloc(&src,fmt,evenw,evenh,64)||!aom_img_alloc(&dst,fmt,evenw,evenh,64))return 1;
    src.d_w=w;src.d_h=h;src.bit_depth=depth;src.monochrome=mono;src.mc=identity?AOM_CICP_MC_IDENTITY:AOM_CICP_MC_BT_601;
    for(int plane=0;plane<3;plane++) {
      int psx=plane?sx:0,psy=plane?sy:0,pw=plane?cw:w,ph=plane?ch:h;
      for(int y=0;y<evenh/(1+psy);y++)for(int x=0;x<evenw/(1+psx);x++) {
        unsigned value=sample(index,plane,x<pw?x:pw-1,y<ph?y:ph-1,depth);
        if(depth==8)src.planes[plane][y*src.stride[plane]+x]=value;
        else ((uint16_t*)(src.planes[plane]+y*src.stride[plane]))[x]=value;
      }
    }
    aom_film_grain_t p;parameters(&p,index,config,scenario,depth);
    if(av1_add_film_grain(&p,&src,&dst)!=0)return 2;
    printf("%d %d %d %d %d %d %d %d %d %d ",index,depth,mono,sx,sy,w,h,mono?0:cw,mono?0:ch,identity);
    for(int plane=0;plane<(mono?1:3);plane++) {
      int pw=plane?cw:w,ph=plane?ch:h;
      for(int y=0;y<ph;y++)for(int x=0;x<pw;x++) {
        unsigned original=depth==8?src.planes[plane][y*src.stride[plane]+x]:((uint16_t*)(src.planes[plane]+y*src.stride[plane]))[x];
        if(original!=sample(index,plane,x,y,depth))return 3;
        unsigned value=depth==8?dst.planes[plane][y*dst.stride[plane]+x]:((uint16_t*)(dst.planes[plane]+y*dst.stride[plane]))[x];
        printf("%u ",value);
      }
    }
    printf("\n");aom_img_free(&src);aom_img_free(&dst);
  }
  return 0;
}
'''
GENERATOR=PARAMETERS+'''
FrameGrainParameters :: (index: s32, config: s32, scenario: s32) -> FilmGrainParams {
    p := NoiseParameters(index, config, scenario)
    p.scaling_shift = 8+scenario; p.overlap_flag = (index+config)%2 != 0
    p.clip_to_restricted_range = (scenario/2+config)%2 != 0
    for plane: 0..2 {
        points := p.scaling_points_y[:]; count := p.num_y_points
        if plane == 1 { points = p.scaling_points_cb[:]; count = p.num_cb_points }
        if plane == 2 { points = p.scaling_points_cr[:]; count = p.num_cr_points }
        for i: 0..count-1 {
            points[i*2] = ifx count == 1 then 128 else cast(s32)i*255/(count-1)
            points[i*2+1] = cast(s32)((i*37+index*17+plane*13)&255)
        }
    }
    p.cb_mult = (index*19)&255; p.cb_luma_mult = (index*73)&255; p.cb_offset = (index*91)&511
    p.cr_mult = (index*29)&255; p.cr_luma_mult = (index*59)&255; p.cr_offset = (index*113)&511
    return p
}
FrameSourceSample :: (index: s32, plane: s32, x: s32, y: s32, depth: s32) -> u16 {
    maximum := cast(s32)((cast(u32)1 << cast(u32)depth)-1)
    if index%4 == 0 {
        if plane == 0 { return 0 }; if plane == 1 { return cast(u16)maximum }; return cast(u16)(maximum/2)
    }
    if index%4 == 2 {
        kind := (x+y+plane)%3
        if kind == 0 { return 0 }; if kind == 1 { return cast(u16)maximum }; return cast(u16)(maximum/2)
    }
    return cast(u16)((x*37+y*71+plane*113+index*97+x*y*3)&maximum)
}
FrameSource :: (index: s32, plane: s32, width: s32, height: s32, depth: s32) -> [4096]u16 {
    source: [4096]u16
    for i: 0..4095 { source[i] = 65535 }
    for y: 0..height-1 { for x: 0..width-1 { source[y*64+x] = FrameSourceSample(index,plane,cast(s32)x,cast(s32)y,depth) } }
    return source
}
'''


def main():
    parser=argparse.ArgumentParser()
    for name in ('root','out','aom'):parser.add_argument('--'+name,type=Path,required=True)
    a=parser.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    if run(['git','-C',str(a.aom),'rev-parse','HEAD'],text=True,capture_output=True).stdout.strip()!=PIN:
        raise SystemExit('libaom pin mismatch')
    run(['git','-C',str(a.aom),'diff','--quiet','HEAD','--'])
    source=a.out/'oracle.c';source.write_text(HOST);host=a.out/'oracle'
    library=Path(os.environ.get('AV1_AOM_LIBRARY',str(a.root/'build/external/lib/libaom.a')))
    config=Path(os.environ.get('AV1_AOM_CONFIG',str(a.root/'build/native/aom')))
    run(shlex.split(os.environ.get('CC','cc'))+['-std=c11','-O2','-I'+str(a.aom),'-I'+str(config),str(source),str(library),'-lm','-lpthread','-o',str(host)])
    count=0;compared=0;changed=0;native_hash=hashlib.sha256()
    with ExitStack() as files:
        targets=[]
        for shard in range(8):
            directory=a.out/f'shard{shard}';directory.mkdir(exist_ok=True)
            target=files.enter_context((directory/'av1_grain_apply_vectors.zi').open('w'));targets.append(target)
            for path in (a.root/'src/av1/grain_apply.zi',a.root/'src/av1/grain_params.zi',a.root/'tests/av1_grain_apply.zi'):
                target.write('#import, file "'+os.path.relpath(path,directory)+'";\n')
            target.write('using Codec :: #import "image_codec/api"\n'+GENERATOR+'\n#program_export\nmain :: () -> s32 {\n    if GrainApplyBounds() != 0 { return 99 }\n')
            for index in range(shard*6,(shard+1)*6):target.write(f'    if Case{index}() != 0 {{ return {index+1} }}\n')
            target.write('    return 0\n}\n')
        errors=files.enter_context((a.out/'oracle.log').open('w'))
        process=subprocess.Popen([str(host)],stdout=subprocess.PIPE,stderr=errors,text=True)
        try:
            for line in process.stdout:
                native_hash.update(line.encode());values=list(map(int,line.split()))
                index,depth,mono,sx,sy,w,h,cw,ch,identity=values[:10];values=values[10:]
                expected_count=w*h+(0 if mono else 2*cw*ch)
                if index!=count or len(values)!=expected_count:raise SystemExit('native grain application result shape mismatch')
                target=targets[index//6];config=(index//4)%4;scenario=index%4
                target.write(f'Case{index} :: () -> s32 {{\n    y := FrameSource({index},0,{w},{h},{depth})\n')
                target.write(f'    u := FrameSource({index},1,{max(1,cw)},{max(1,ch)},{depth}); v := FrameSource({index},2,{max(1,cw)},{max(1,ch)},{depth})\n')
                target.write('    input: GrainPictureView; input.y = y[:]; input.u = u[:]; input.v = v[:]; input.y_stride = 64; input.chroma_stride = 64\n')
                target.write(f'    input.width = {w}; input.height = {h}; input.monochrome = {str(bool(mono)).lower()}; input.subsampling_x = {sx}; input.subsampling_y = {sy}; input.bit_depth = {depth}; input.matrix_identity = {str(bool(identity)).lower()}\n')
                target.write(f'    parameters := FrameGrainParameters({index},{config},{scenario})\n    result := ApplyFilmGrain64(input, parameters)\n')
                target.write(f'    if result.error.code != DecodeOK || result.width != {w} || result.height != {h} || result.chroma_width != {cw} || result.chroma_height != {ch} {{ return 1 }}\n')
                for plane,(name,pw,ph) in enumerate((('y',w,h),('u',cw,ch),('v',cw,ch))):
                    if mono and plane:continue
                    for base in range(0,pw*ph,1024):target.write(f'    if Check{index}_{plane}_{base}(result.{name}[:]) != 0 {{ return {plane+2} }}\n')
                    target.write(f'    for row: 0..{ph-1} {{ for column: 0..{pw-1} {{ if {name}[row*64+column] != FrameSourceSample({index},{plane},cast(s32)column,cast(s32)row,{depth}) {{ return 5 }} }} }}\n')
                target.write(f'    for j: 0..4095 {{ if (j/64 >= {h} || j%64 >= {w}) && result.y[j] != 0 {{ return 6 }}\n')
                target.write(f'        if (j/64 >= {ch} || j%64 >= {cw}) && (result.u[j] != 0 || result.v[j] != 0) {{ return 7 }} }}\n    return 0\n}}\n')
                offset=0
                for plane,(pw,ph) in enumerate(((w,h),(cw,ch),(cw,ch))):
                    if mono and plane:continue
                    samples=values[offset:offset+pw*ph];offset+=pw*ph
                    maximum=(1<<depth)-1
                    def original(x,y):
                        if scenario==0:return 0 if plane==0 else maximum if plane==1 else maximum//2
                        if scenario==2:return (0,maximum,maximum//2)[(x+y+plane)%3]
                        return (x*37+y*71+plane*113+index*97+x*y*3)&maximum
                    changed+=sum(value!=original(j%pw,j//pw) for j,value in enumerate(samples))
                    for base in range(0,len(samples),1024):
                        target.write(f'Check{index}_{plane}_{base} :: (actual: []u16) -> s32 {{\n')
                        for start in range(base,min(base+1024,len(samples)),64):
                            chunk=samples[start:start+64]
                            target.write('    {\n        expected: ['+str(len(chunk))+']u16 = .['+','.join(map(str,chunk))+']\n')
                            target.write(f'        for j: 0..{len(chunk)-1} {{ index := {start}+j; if actual[(index/{pw})*64+index%{pw}] != expected[j] {{ return 1 }} }}\n    }}\n')
                        target.write('    return 0\n}\n')
                compared+=len(values);count+=1
            code=process.wait()
            if code:raise SystemExit(f'native grain application exited {code}; see {a.out / "oracle.log"}')
        except BaseException:
            if process.poll() is None:process.kill()
            process.wait();raise
        finally:process.stdout.close()
    if count!=48 or not changed:raise SystemExit('native grain application coverage incomplete')
    (a.out/'oracle.json').write_text(json.dumps(dict(revision=PIN,library_sha256=digest(library),native_host_sha256=hashlib.sha256(HOST.encode()).hexdigest(),native_output_sha256=native_hash.hexdigest(),
        vectors=count,shards=8,compared_samples=compared,changed_samples=changed,depths=[8,10,12],configs=['mono','420','422','444'],dimensions=[[1,1],[7,5],[33,35],[64,64]],
        scope='bounded complete film-grain application to raw native pictures; not encoded-frame or decoder integration conformance'),indent=2)+'\n')
    print(f'Pinned grain application: {count} raw pictures, {compared} samples, {changed} changed samples')


if __name__=='__main__':main()
