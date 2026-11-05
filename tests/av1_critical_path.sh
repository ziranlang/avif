#!/bin/sh
# Run through build-queue. This suite preserves the facade/default and reports
# the current narrow authored scope explicitly; no full-AV1 claim is implied.
set -eu
. "$(dirname -- "$0")/common.sh"
python3 - "$root" "$toolchain" <<'PY'
import hashlib,json,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]);toolchain=pathlib.Path(sys.argv[2]);out=root/'build/scratch/av1'
out.mkdir(parents=True,exist_ok=True)
def digest(path):
    hasher=hashlib.sha256()
    with path.open('rb') as binary:
        for chunk in iter(lambda:binary.read(1024*1024),b''):hasher.update(chunk)
    return hasher.hexdigest()
(out/'toolchain-start.json').write_text(json.dumps(dict(
    revision=subprocess.run(['git','-C',str(toolchain),'rev-parse','HEAD'],check=True,text=True,capture_output=True).stdout.strip(),
    binary_sha256={name:digest(toolchain/'build/bin'/name) for name in ('ziran','zi2zir','zi2c','zi2go','zi2zx','zi2zx-vm')}),indent=2)+'\n')
files=sorted((root/'src/av1').rglob('*'))+sorted((root/'tests').glob('av1_*'))+[root/'tests/common.sh',root/'docs/AV1.md']
(out/'sources-start.json').write_text(json.dumps({str(path.relative_to(root)):digest(path) for path in files if path.is_file()},indent=2)+'\n')
(out/'stages-passed.txt').write_text('')
PY
for stage in obu_range headers entropy_tiles reconstruction scalar_kernels prediction filter_intra directional palette cfl chroma color_palette color_palette_boundaries key_frames key_controls coefficients still_partitions boundaries filter_kernels grain_kernels grain_frames engine_parity; do
    sh "tests/av1_$stage.sh"
    printf '%s\n' "$stage" >> "$root/build/scratch/av1/stages-passed.txt"
done
python3 - "$root" "$toolchain" <<'PY'
import datetime,hashlib,json,os,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]);toolchain=pathlib.Path(sys.argv[2])
def digest(path):
    hasher=hashlib.sha256()
    with path.open('rb') as binary:
        for chunk in iter(lambda:binary.read(1024*1024),b''):hasher.update(chunk)
    return hasher.hexdigest()
files=sorted((root/'src/av1').rglob('*'))+sorted((root/'tests').glob('av1_*'))+[root/'tests/common.sh',root/'docs/AV1.md']
before=json.loads((root/'build/scratch/av1/toolchain-start.json').read_text())
binaries={name:digest(toolchain/'build/bin'/name) for name in ('ziran','zi2zir','zi2c','zi2go','zi2zx','zi2zx-vm')}
if before['binary_sha256']!=binaries:raise SystemExit('Toolchain binaries changed during AV1 suite; no integrated pass receipt written')
sources={str(path.relative_to(root)):digest(path) for path in files if path.is_file()}
if json.loads((root/'build/scratch/av1/sources-start.json').read_text())!=sources:
    raise SystemExit('Owned AV1 source/test inputs changed during AV1 suite; no integrated pass receipt written')
stages='obu_range headers entropy_tiles reconstruction scalar_kernels prediction filter_intra directional palette cfl chroma color_palette color_palette_boundaries key_frames key_controls coefficients still_partitions boundaries filter_kernels grain_kernels grain_frames engine_parity'.split()
if (root/'build/scratch/av1/stages-passed.txt').read_text().splitlines()!=stages:
    raise SystemExit('Owned AV1 stage completion list is incomplete; no integrated pass receipt written')
receipt=dict(command='build-queue -- sh tests/av1_critical_path.sh',exit_code=0,
    recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    dependency_source_overrides={key:os.environ[key] for key in ('IMAGE_CODEC_ROOT','AV1_AOM_SOURCE','AV1_DAV1D_SOURCE') if key in os.environ},
    implementation_status='incomplete: bounded lossless shown KEY decode including film grain validated; deblock/CDEF/restoration scalar kernels validated separately from frame integration',
    supported_authored_decode='dimensions1..64 lossless shown KEY mono/420/422/444 at8/10/12-bit with reduced or full headers, size overrides/frame IDs/timing and film grain; all13 intra modes/all7 angle deltas, CfL,all5 filter-intra predictors, Y/UV palettes2..8 and all10 partition types subject to normative subsampling restrictions',
    full_av1_conformance=False,facade_default_changed=False,committed=False,pushed=False,released=False,installed=False,
    unimplemented=['dimensions or sequence maxima above64','multi-tile reconstruction','intraBC','lossy transforms/entropy','hidden/inter/intra-only frames and retained reference state',
        'frame-level deblock/CDEF/restoration','exact raw-YUV output cap pending shared dimension-only validation API','full AVIF fixture compatibility','full pinned plane corpus','performance measurement'],
    source_sha256=sources,source_inputs_unchanged=True,stages_passed=stages,
    stage_receipts={name:json.loads((root/'build/scratch'/name/'receipt.json').read_text())
        for name in ('av1','av1-headers','av1-tiles','av1-lossless','av1-scalar','av1-prediction','av1-filter-intra','av1-directional','av1-palette','av1-cfl','av1-chroma','av1-color-palette','av1-color-palette-boundaries','av1-key-frames','av1-key-controls','av1-still','av1-boundaries','av1-filter-kernels','av1-grain-kernels','av1-grain-frames','av1-engine')},
    toolchain_revision_start=before['revision'],
    toolchain_revision=subprocess.run(['git','-C',str(toolchain),'rev-parse','HEAD'],check=True,text=True,capture_output=True).stdout.strip(),
    toolchain_binary_sha256=binaries,toolchain_binaries_unchanged=True)
(root/'build/scratch/av1/critical-path-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
PY
printf '%s\n' 'Owned AV1 local stage suite passed; general AV1 engine, full conformance and performance remain unfinished'
