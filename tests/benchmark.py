"""Collect real complete-codec .zi runner measurements; no decoder in Python."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

p = argparse.ArgumentParser()
p.add_argument('--input', required=True, type=Path)
p.add_argument('--expected', required=True, type=Path)
p.add_argument('--output', required=True, type=Path)
p.add_argument('--local-only', action='store_true')
a=p.parse_args()
root=Path(__file__).resolve().parent.parent
runner=root/'build/bin/avif-bench'
out=a.output.resolve(); out.parent.mkdir(parents=True,exist_ok=True)
def digest(path):
    with open(path,'rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
model=None; flags=None
with open('/proc/cpuinfo') as f:
    for line in f:
        if model is None and line.startswith('model name'): model=line.partition(':')[2].strip()
        if flags is None and line.startswith('flags'): flags=line.partition(':')[2].split()
        if model is not None and flags is not None: break
reports=[]
for engine in ('aom','dav1d'):
    log=out.parent/(out.stem+'-'+engine+'.json')
    with log.open('wb') as target:
        start=time.perf_counter_ns()
        child=subprocess.Popen([str(runner),str(a.input.resolve()),str(a.expected.resolve()),engine],stdout=target)
        _, status, usage=os.wait4(child.pid,0)
        child.returncode=os.waitstatus_to_exitcode(status)
        elapsed=time.perf_counter_ns()-start
    if child.returncode:
        raise RuntimeError(f'{engine} runner failed {child.returncode}; inspect {log}')
    report=json.loads(log.read_text())
    assert report['correctness_verified'] and report['active_workers']==1
    assert len(report['samples_ns'])==16 and report['p95_ns']>=report['p50_ns']>=0
    report['process_cpu_ns']=round((usage.ru_utime+usage.ru_stime)*1e9)
    report['process_elapsed_ns']=elapsed
    report['process_peak_rss_bytes']=usage.ru_maxrss*1024
    report['process_metrics_scope']='entire process: metadata decode, correctness preflight, 16 timed decodes, hashes/validation/serialization/destruction'
    reports.append(report)
assert reports[0]['output_hash']==reports[1]['output_hash']
artifact=Path((root/'build/scratch/avif/dav1d-artifact.txt').read_text().strip())
result={'schema':1,'kind':'full-file-to-RGBA8','claims':'local warm comparison; no fastest or 10x claim',
    'input':str(a.input.resolve()),'input_sha256':digest(a.input),'expected_sha256':digest(a.expected),
    'local_only_source':a.local_only,'runner_sha256':digest(runner),
    'toolchain_executable_sha256':digest(Path(os.environ['ZIRAN'])),
    'cpu_model':model,'cpu_flags':flags,'allowed_cpus':sorted(os.sched_getaffinity(0)),
    'artifact_provenance':json.loads((artifact.parent/'provenance.json').read_text()),
    'reports':reports,
    'dav1d_vs_aom_p50_ratio':reports[0]['p50_ns']/reports[1]['p50_ns'] if reports[1]['p50_ns'] else None,
    'unmeasured':['allocator calls','energy','cold cache','hardware engines','other machines','latest libavif/libaom conversion stack']}
out.write_text(json.dumps(result,indent=2)+'\n')
print('Full-codec comparison validated and recorded:',out)
