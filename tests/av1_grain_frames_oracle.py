#!/usr/bin/env python3
"""Real pinned encoder grain KEY frames, native metadata and displayed planes."""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import shlex
from av1_chroma_oracle import HOST as DECODER
from av1_frame_oracle import zi_bytes
from av1_grain_params_oracle import FIELDS, BOOLS
from av1_lossless_oracle import PIN, digest, run

ENCODER=r'''
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include "aom/aom_encoder.h"
#include "aom/aomcx.h"
static int control(aom_codec_ctx_t *c,int id,int value) {
  if(aom_codec_control(c,id,value)){fprintf(stderr,"grain control%d: %s / %s\n",id,aom_codec_error(c),aom_codec_error_detail(c));return 1;}return 0;
}
int main(int argc,char **argv) {
  if(argc!=7)return 1;int w=atoi(argv[2]),h=atoi(argv[3]),depth=atoi(argv[4]),format=atoi(argv[5]),vector=atoi(argv[6]);
  aom_codec_enc_cfg_t cfg;if(aom_codec_enc_config_default(aom_codec_av1_cx(),&cfg,AOM_USAGE_GOOD_QUALITY))return 2;
  cfg.g_w=w;cfg.g_h=h;cfg.g_threads=1;cfg.g_lag_in_frames=0;cfg.g_limit=0;cfg.g_timebase.num=1;cfg.g_timebase.den=30;
  cfg.g_bit_depth=(aom_bit_depth_t)depth;cfg.g_input_bit_depth=depth;cfg.monochrome=format==0;
  cfg.g_profile=depth==12||format==2?2:format==3?1:0;cfg.rc_end_usage=AOM_Q;cfg.rc_min_quantizer=cfg.rc_max_quantizer=0;
  aom_codec_ctx_t codec={0};if(aom_codec_enc_init(&codec,aom_codec_av1_cx(),&cfg,depth>8?AOM_CODEC_USE_HIGHBITDEPTH:0))return 3;
  if(control(&codec,AOME_SET_CPUUSED,8)||control(&codec,AV1E_SET_LOSSLESS,1)||control(&codec,AV1E_SET_FORCE_VIDEO_MODE,1)||
     control(&codec,AV1E_SET_ENABLE_CDEF,0)||control(&codec,AV1E_SET_ENABLE_RESTORATION,0)||control(&codec,AV1E_SET_ENABLE_INTRABC,0)||
     control(&codec,AV1E_SET_ENABLE_PALETTE,0)||control(&codec,AV1E_SET_ENABLE_FILTER_INTRA,0)||
     control(&codec,AV1E_SET_FILM_GRAIN_TEST_VECTOR,vector))return 4;
  aom_img_fmt_t fmt=format==3?AOM_IMG_FMT_I444:format==2?AOM_IMG_FMT_I422:AOM_IMG_FMT_I420;
  if(depth>8)fmt=(aom_img_fmt_t)(fmt|AOM_IMG_FMT_HIGHBITDEPTH);
  aom_image_t image;if(!aom_img_alloc(&image,fmt,w,h,64))return 5;image.bit_depth=depth;
  for(int plane=0;plane<3;plane++) {
    int sx=plane?image.x_chroma_shift:0,sy=plane?image.y_chroma_shift:0;
    int pw=(w+sx)/(1+sx),ph=(h+sy)/(1+sy),maximum=(1<<depth)-1;
    for(int y=0;y<ph;y++)for(int x=0;x<pw;x++) {
      unsigned value=plane==0?(maximum/2+2):plane==1?maximum/4:maximum-3;
      if(depth==8)image.planes[plane][y*image.stride[plane]+x]=value;
      else ((uint16_t*)(image.planes[plane]+y*image.stride[plane]))[x]=value;
    }
  }
  FILE *out=fopen(argv[1],"wb");if(!out)return 6;int frames=0;
  for(int pass=0;pass<2;pass++) {
    if(aom_codec_encode(&codec,pass?NULL:&image,pass,1,0))return 7;
    aom_codec_iter_t it=NULL;const aom_codec_cx_pkt_t *packet;
    while((packet=aom_codec_get_cx_data(&codec,&it)))if(packet->kind==AOM_CODEC_CX_FRAME_PKT) {
      if(fwrite(packet->data.frame.buf,1,packet->data.frame.sz,out)!=packet->data.frame.sz)return 8;frames++;
    }
  }
  if(fclose(out)||frames!=1)return 9;aom_img_free(&image);return aom_codec_destroy(&codec);
}
'''


def main():
    parser=argparse.ArgumentParser()
    for name in ('root','out','aom'):parser.add_argument('--'+name,type=Path,required=True)
    a=parser.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    if run(['git','-C',str(a.aom),'rev-parse','HEAD'],text=True,capture_output=True).stdout.strip()!=PIN:raise SystemExit('libaom pin mismatch')
    run(['git','-C',str(a.aom),'diff','--quiet','HEAD','--'])
    library=Path(os.environ.get('AV1_AOM_LIBRARY',str(a.root/'build/external/lib/libaom.a')))
    config=Path(os.environ.get('AV1_AOM_CONFIG',str(a.root/'build/native/aom')))
    encoder_library=Path(os.environ.get('AV1_AOM_ENCODER_LIBRARY',str(a.root/'build/scratch/av1-key-controls/aom/libaom.a')))
    compiler=shlex.split(os.environ.get('CC','cc'))
    source=a.out/'encoder.c';source.write_text(ENCODER);encoder=a.out/'encoder'
    run(compiler+['-std=c11','-O2','-I'+str(a.aom),'-I'+str(encoder_library.parent),str(source),str(encoder_library),'-lm','-lpthread','-o',str(encoder)])
    native=DECODER.replace('static int blocks,cfl,palette_y,palette_uv;',
        'static int blocks,cfl,palette_y,palette_uv,mono,grain_present;static aom_film_grain_t observed;')
    native=native.replace('blocks++;','blocks++;observed=p->common.film_grain_params;mono=p->common.seq_params->monochrome;grain_present=p->common.seq_params->film_grain_params_present;')
    native=native.replace('||!image->planes[1]||!image->planes[2]','')
    native=native.replace('for(int plane=0;plane<3;plane++) {','for(int plane=0;plane<3;plane++) {if(mono&&plane){printf("\\n");continue;}')
    fields='printf("%d %d ",mono,grain_present);'+''.join(f'printf("%d ",(int)observed.{expression});' for _,expression in FIELDS)+'printf("\\n");'
    native=native.replace('return aom_codec_destroy(&codec);',fields+'return aom_codec_destroy(&codec);')
    source=a.out/'decoder.c';source.write_text(native);decoder=a.out/'decoder'
    run(compiler+['-std=c11','-O2','-I'+str(a.aom),'-I'+str(config),str(source),str(library),'-Wl,--wrap=av1_read_mode_info','-lm','-lpthread','-o',str(decoder)])
    records=[];compared=0;prefixes=0;allocation_case=None
    with ExitStack() as files:
        targets=[];directories=[]
        for shard in range(8):
            directory=a.out/f'shard{shard}';directory.mkdir(exist_ok=True);directories.append(directory)
            target=files.enter_context((directory/'av1_grain_frames_vectors.zi').open('w'));targets.append(target)
            target.write('#import, file "'+os.path.relpath(a.root/'src/av1/decoder.zi',directory)+'";\nusing Codec :: #import "image_codec/api"\n')
            target.write('#program_export\nmain :: () -> s32 {\n')
            for index in range(shard*6,(shard+1)*6):target.write(f'    if Case{index}() != 0 {{ return {index+1} }}\n')
            target.write('    return 0\n}\nPutBytes :: (target: []u8, offset: s64, source: []u8) { for i: 0..source.count-1 { target[offset+i] = source[i] } }\n')
        for index in range(48):
            depth=8+2*(index//16);format=(index//4)%4;scenario=index%4
            w,h=((1,1),(7,5),(33,35),(64,64))[scenario];vector=1+(index%16)
            path=a.out/f'frame-{index}.obu';command=[str(encoder),str(path),str(w),str(h),str(depth),str(format),str(vector)]
            run(command)
            output=run([str(decoder),str(path)],text=True,capture_output=True).stdout.splitlines()
            if len(output)!=6:raise SystemExit('native grain frame output shape mismatch')
            dimensions=list(map(int,output[0].split()));metadata=list(map(int,output[5].split()))
            mono=format==0;sx=int(format!=3);sy=int(format<2)
            if dimensions!=[w,h,depth,sx,sy] or metadata[:2]!=[int(mono),1] or len(metadata)!=len(FIELDS)+2 or metadata[2]!=1:
                raise SystemExit(f'encoder did not expose active grain for case{index}: {dimensions} {metadata[:4]}')
            pixels=[list(map(int,line.split())) for line in output[1:4]]
            cw=(w+sx)//(1+sx);ch=(h+sy)//(1+sy)
            if list(map(len,pixels))!=[w*h,0 if mono else cw*ch,0 if mono else cw*ch]:raise SystemExit('native grain frame plane count mismatch')
            # Encoded packet is bounded by the decoder oracle's64KiB input cap.
            if path.stat().st_size>=65536:raise SystemExit('grain frame input exceeds oracle cap')
            data=list(path.read_bytes());target=targets[index//6];byte_count=1 if depth==8 else 2
            body,loaders=zi_bytes('bytes',data,f'Grain{index}');target.write(f'Case{index} :: () -> s32 {{\n'+body)
            target.write('    options := DefaultOptions(); budget := NewWorkerBudget(options.limits); options.workers = *budget\n')
            target.write('    image := DecodeAv1YUV(BorrowBytes(bytes[:]), *options)\n    if !image.is_ok { return 100+cast(s32)image.error.code }\n')
            target.write(f'    if image.y.width != {w} || image.y.height != {h} || image.y.storage.count != {w*h*byte_count} || image.u.storage.count != {0 if mono else cw*ch*byte_count} || image.v.storage.count != {0 if mono else cw*ch*byte_count} {{ return 1 }}\n')
            target.write('    if budget.active_workers != 0 || budget.working_bytes != 0 || !image.sequence.film_grain_params_present { return 2 }\n')
            for (field,_),value in zip(FIELDS,metadata[2:]):
                expected=str(bool(value)).lower() if field in BOOLS else str(value)
                target.write(f'    if image.frame.grain_parameters.{field} != {expected} {{ return 3 }}\n')
            for plane,(name,samples) in enumerate(zip(('y','u','v'),pixels)):
                for base in range(0,len(samples),1024):target.write(f'    if Check{index}_{plane}_{base}(*image.{name}) != 0 {{ return 4 }}\n')
            total=(w*h+(0 if mono else 2*cw*ch))*byte_count
            # Shared DecodeOptions currently defines RGBA8 dimension validation.
            # A reusable raw-dimension API is requested upstream; do not bypass
            # that stable API or pretend this proves exact raw-YUV cap support.
            shared_cap=max(total,4*w*h)
            target.write(f'    options.limits.max_output_bytes = {shared_cap-1}\n    limited := DecodeAv1YUV(BorrowBytes(bytes[:]), *options)\n')
            target.write('    if limited.is_ok || limited.error.code != LimitExceeded || limited.y.storage.count != 0 || limited.u.storage.count != 0 || limited.v.storage.count != 0 || budget.active_workers != 0 || budget.working_bytes != 0 { return 5 }\n')
            target.write(f'    options.limits.max_output_bytes = {shared_cap}\n    second := DecodeAv1YUV(BorrowBytes(bytes[:]), *options)\n')
            target.write('    if !second.is_ok { return 6 }\n    original := image.y.storage[0]; image.y.storage[0] = original ^ 1\n    if second.y.storage[0] != original { return 7 }; image.y.storage[0] = original\n')
            if scenario==0:
                target.write(f'    for end: 0..{len(data)-1} {{\n        partial := DecodeAv1YUV(BorrowBytes(bytes[:end]), *options)\n')
                target.write('        if partial.is_ok || partial.error.code == DecodeOK || partial.y.storage.count != 0 || partial.u.storage.count != 0 || partial.v.storage.count != 0 || budget.active_workers != 0 || budget.working_bytes != 0 { return 8 }\n    }\n')
                prefixes+=len(data)
            target.write('    bytes[0] = 0\n')
            for plane,(name,samples) in enumerate(zip(('y','u','v'),pixels)):
                for base in range(0,len(samples),1024):target.write(f'    if Check{index}_{plane}_{base}(*image.{name}) != 0 {{ return 9 }}\n')
            target.write('    return 0\n}\n'+loaders)
            for plane,samples in enumerate(pixels):
                for base in range(0,len(samples),1024):
                    target.write(f'Check{index}_{plane}_{base} :: (actual: *Plane) -> s32 {{\n')
                    for offset in range(base,min(base+1024,len(samples)),64):
                        chunk=samples[offset:offset+64]
                        target.write('    {\n        expected: ['+str(len(chunk))+']u16 = .['+','.join(map(str,chunk))+']\n')
                        target.write(f'        for j: 0..{len(chunk)-1} {{ at := ({offset}+j)*{byte_count}; value := cast(u16)actual.storage[at]\n')
                        if byte_count==2:target.write('            value |= cast(u16)actual.storage[at+1] << 8\n')
                        target.write('            if value != expected[j] { return 1 }\n        }\n    }\n')
                    target.write('    return 0\n}\n')
            if allocation_case is None and not mono:allocation_case=data
            compared+=sum(map(len,pixels))
            records.append(dict(depth=depth,format=format,width=w,height=h,grain_vector=vector,encoded_bytes=len(data),sha256=digest(path),encoder_command=command))
    directory=a.out/'allocation';directory.mkdir(exist_ok=True)
    body,loaders=zi_bytes('bytes',allocation_case,'GrainAllocation')
    (directory/'av1_grain_allocation.zi').write_text('#import, file "'+os.path.relpath(a.root/'src/av1/decoder.zi',directory)+'";\nusing Codec :: #import "image_codec/api"\n'+
        'PutBytes :: (target: []u8, offset: s64, source: []u8) { for i: 0..source.count-1 { target[offset+i] = source[i] } }\n#program_export\nGrainAllocationFailure :: () -> s32 {\n'+body+
        '    options := DefaultOptions(); budget := NewWorkerBudget(options.limits); options.workers = *budget\n    image := DecodeAv1YUV(BorrowBytes(bytes[:]), *options)\n'+
        '    if image.is_ok || image.error.code != AllocationFailed || image.y.storage.count != 0 || image.u.storage.count != 0 || image.v.storage.count != 0 || budget.active_workers != 0 || budget.working_bytes != 0 { return 1 }\n    return 0\n}\n'+loaders)
    (a.out/'oracle.json').write_text(json.dumps(dict(revision=PIN,library_sha256=digest(library),encoder_library_sha256=digest(encoder_library),native_host_sha256=hashlib.sha256(native.encode()).hexdigest(),
        vectors=48,shards=8,compared_samples=compared,grain_fields=len(FIELDS),truncated_prefixes=prefixes,depths=[8,10,12],configs=['mono','420','422','444'],
        output_cap_contract='max(aggregate source YUV bytes,shared RGBA8 dimension floor); exact raw-YUV cap awaits upstream ValidatePixelDimensions',
        fixtures=records,scope='real displayed lossless grain KEY frames<=64; lossy/larger/inter/filter pipeline remains unsupported'),indent=2)+'\n')
    print(f'Pinned encoded grain:48 KEY frames, {compared} displayed samples, {prefixes} prefixes, {len(FIELDS)} grain fields')


if __name__=='__main__':main()
