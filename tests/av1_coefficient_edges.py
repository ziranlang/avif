#!/usr/bin/env python3
"""Encode genuine AV1 lossless coefficient boundary syntax with the pinned
upstream arithmetic encoder. Valid whole frames must also decode in libaom.
These are specification boundary tests, not a general conformance corpus.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

HOST = r'''
#include <stdio.h>
#include <stdint.h>
#include "aom_dsp/entenc.h"
#include "aom_dsp/prob.h"
int main(void) {
 unsigned count;
 while(scanf("%u",&count)==1) {
   if(count>32)return 1;uint16_t cdf[32][17];unsigned n[32];
   for(unsigned i=0;i<count;i++) {
     if(scanf("%u",n+i)!=1||n[i]<2||n[i]>16)return 2;
     for(unsigned j=0;j<n[i];j++) {unsigned x;if(scanf("%u",&x)!=1||x>32768)return 3;cdf[i][j]=32768-x;}
     cdf[i][n[i]]=0;
   }
   unsigned operations;if(scanf("%u",&operations)!=1||operations>4096)return 4;
   od_ec_enc encoder;od_ec_enc_init(&encoder,4096);
   for(unsigned i=0;i<operations;i++) {
     unsigned table,symbol,adapt;
     if(scanf("%u%u%u",&table,&symbol,&adapt)!=3||table>=count||symbol>=n[table])return 5;
     od_ec_encode_cdf_q15(&encoder,symbol,cdf[table],n[table]);
     if(adapt)update_cdf(cdf[table],symbol,n[table]);
   }
   uint32_t size;unsigned char *data=od_ec_enc_done(&encoder,&size);
   if(!data||!size||size>4096)return 6;
   printf("%u",size);for(unsigned i=0;i<size;i++)printf(" %u",data[i]);printf("\n");
   od_ec_enc_clear(&encoder);
 }
 return 0;
}
'''


def run(command, **kwargs):return subprocess.run(command,check=True,**kwargs)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--aom',type=Path,required=True)
    args=parser.parse_args()
    pin='d772e334cc724105040382a977ebb10dfd393293'
    if run(['git','-C',str(args.aom),'rev-parse','HEAD'],text=True,capture_output=True).stdout.strip()!=pin:
        raise SystemExit('libaom pin mismatch')
    run(['git','-C',str(args.aom),'diff','--quiet','HEAD','--'])
    args.out.mkdir(parents=True,exist_ok=True)
    source=args.out/'edge_encoder.c';source.write_text(HOST)
    host=args.out/'edge_encoder'
    config=Path(os.environ.get('AV1_AOM_CONFIG',str(args.root/'build/native/aom')))
    library=Path(os.environ.get('AV1_AOM_LIBRARY',str(args.root/'build/external/lib/libaom.a')))
    run(shlex.split(os.environ.get('CC','cc'))+['-std=c11','-O2','-I'+str(args.aom),'-I'+str(config),
        str(source),str(args.aom/'aom_dsp/entenc.c'),str(library),'-lm','-o',str(host)])
    # Read only the corresponding pinned probability definitions. Product
    # constants are checked independently against their upstream provenance.
    upstream=(args.aom/'av1/common/token_cdfs.h').read_text()
    product=(args.root/'src/av1/cdfs4.zi').read_text()
    definitions=[('skip',7,2,'av1_default_txb_skip_cdfs'),('dc',3,2,'av1_default_dc_sign_cdfs'),
        ('eob',1,5,'av1_default_eob_multi16_cdfs'),('extra',3,2,'av1_default_eob_extra_cdfs'),
        ('base_eob',4,3,'av1_default_coeff_base_eob_multi_cdfs'),('base',42,4,'av1_default_coeff_base_multi_cdfs'),
        ('br',21,4,'av1_default_coeff_lps_multi_cdfs')]
    tables={}
    for field,count,size,name in definitions:
        text=upstream.split(name,1)[1].split('= {',1)[1]
        rows=[]
        for match in re.finditer(r'AOM_CDF'+str(size)+r'\(([^)]+)\)',text):
            rows.append([eval(value.strip(),{'__builtins__':{}},{}) for value in match[1].split(',')]+[32768])
            if len(rows)==count:break
        if len(rows)!=count:raise SystemExit('missing upstream constants: '+field)
        expected=[value for row in rows for value in row+[0]]
        literal=re.search(r'\b'+field+r': \[\d+\]u16 = \.\[([^]]+)\]',product)
        if literal is None or list(map(int,literal[1].split(',')))!=expected:
            raise SystemExit('product default CDF differs from pinned source: '+field)
        tables[field]=rows
    selected=[tables['skip'][1],tables['eob'][0],tables['base_eob'][0],tables['br'][0],tables['dc'][0],
        [16384,32768],[19132,25510,30392,32768],[31671,32768],
        [15588,17027,19338,20218,20682,21110,21825,23244,24189,28165,29093,30466,32768]]
    def encode(operations):
        text=str(len(selected))+'\n'+''.join(str(len(row))+' '+' '.join(map(str,row))+'\n' for row in selected)
        text+=str(len(operations))+'\n'+''.join(f'{table} {symbol} {adapt}\n' for table,symbol,adapt in operations)
        output=list(map(int,run([str(host)],input=text,text=True,capture_output=True).stdout.split()))
        if output[0]!=len(output)-1:raise SystemExit('encoder output mismatch')
        return bytes(output[1:])
    def operations(level,sign,invalid=False):
        # all_zero=0, EOB=1, coeff_base_eob=3, four BR extensions=3,
        # DC sign, then the normative Golomb suffix for level >= 15.
        result=[(0,0,1),(1,0,1),(2,2,1)]+[(3,3,1)]*4+[(4,sign,1)]
        binary=bin(level-14)[2:]
        bits=('0'*20+'1') if invalid else '0'*(len(binary)-1)+binary
        return result+[(5,int(bit),0) for bit in bits]
    cases=[]
    for level in (15,16,31,255,65535,524287,1048575,1048576,1048589):
        for sign in (0,1):
            encoded=encode(operations(level,sign))
            cases.append(dict(level=level,sign=sign,data=list(encoded),malformed=False))
    cases.append(dict(level=15,sign=0,data=list(encode(operations(15,0,True))),malformed=True))
    # Wrapping cases mask the DC coefficient to zero. Their full-frame plane
    # is conforming and independently verified by the actual native decoder.
    verified=[]
    for sign in (0,1):
        encoded=encode([(6,0,1),(7,0,1),(8,0,1)]+operations(1048576,sign)+[(0,1,1)]*3)
        prefix=bytes([18,0,10,5,24,8,191,33,80,50])
        if len(encoded)+2>=128:raise SystemExit('fixture needs wider length')
        # The verified reduced-still frame header is TWO bytes (16,0).
        # The final 48 in the known zero fixture is its one-byte tile.
        obu=args.out/f'wrap-{sign}.obu';obu.write_bytes(prefix+bytes([len(encoded)+2,16,0])+encoded)
        output=run([str(args.out/'oracle'),str(obu)],text=True,capture_output=True).stdout.splitlines()
        if list(map(int,output[0].split()))!=[8]+[128]*64:raise SystemExit('native wrapping plane mismatch')
        verified.append(str(obu.name))
    relative=os.path.relpath(args.root/'src/av1/coefficients.zi',args.out)
    cdfs=os.path.relpath(args.root/'src/av1/cdfs4.zi',args.out)
    lines=['#import, file "'+relative+'";','#import, file "'+cdfs+'";',
        '#import, file "'+os.path.relpath(args.root/'src/av1/decoder.zi',args.out)+'";',
        '#import, file "'+os.path.relpath(args.root/'src/av1/range.zi',args.out)+'";',
        'using Codec :: #import "image_codec/api"','#program_export','main :: () -> s32 {']
    for case in cases:
        lines+=['    {','        bytes: ['+str(len(case['data']))+']u8 = .['+','.join(map(str,case['data']))+']',
            '        decoder := NewRange(BorrowBytes(bytes[:]), 0, bytes.count)',
            '        cdfs := NewCoeffCDF4x4()',
            '        block := ReadLosslessCoefficients4x4(*decoder, *cdfs, 1, 0)']
        if case['malformed']:
            lines+=['        if block.error.code != MalformedInput { return 1 }']
        else:
            magnitude=case['level']&1048575
            signed=-magnitude if case['sign'] else magnitude
            lines+=[f'        if block.error.code != DecodeOK || block.eob != 1 || block.quant[0] != {signed} {{ return 2 }}',
                f'        if block.level != {min(magnitude,63)} || block.dc_category != {1 if case["sign"] else 2} {{ return 3 }}',
                '        for i: 1..15 { if block.quant[i] != 0 { return 4 } }',
                '        if FinishRange(*decoder).code != DecodeOK { return 5 }']
        lines+=['    }']
    for name in verified:
        data=list((args.out/name).read_bytes())
        lines+=['    {','        bytes: ['+str(len(data))+']u8 = .['+','.join(map(str,data))+']',
            '        options := DefaultOptions()',
            '        budget := NewWorkerBudget(options.limits); options.workers = *budget',
            '        image := DecodeAv1YUV(BorrowBytes(bytes[:]), *options)',
            '        if !image.is_ok || image.y.storage.count != 64 { return 6 }',
            '        for i: 0..63 { if image.y.storage[i] != 128 { return 7 } }',
            '        if budget.active_workers != 0 || budget.working_bytes != 0 { return 8 }','    }']
    lines+=['    return 0','}']
    (args.out/'av1_coefficient_edges.zi').write_text('\n'.join(lines)+'\n')
    (args.out/'edge_oracle.json').write_text(json.dumps(dict(revision=pin,cases=len(cases),
        whole_frame_native_verified=verified,scope='coefficient/Golomb boundary syntax; full conformance pending'),indent=2)+'\n')
    print(f'Coefficient boundaries: {len(cases)} pinned arithmetic streams; two native whole-frame wrap cases; ported CDF constants verified')


if __name__=='__main__':main()
