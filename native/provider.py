#!/usr/bin/env python3
"""Dependency-owned native build recipe (build tooling only)."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

PINS = {'libavif': '1aadfad932c98c069a1204261b1856f81f3bc199',
        'libaom': 'b141d9c45db236335351c8a4b2a14b3ade27c937',
        'dav1d': '54706fc6bc0cdecab7e9593974a4039cc038fca7'}
VERSIONS = {'libavif': '1.3.0', 'libaom': '3.15.3', 'dav1d': '1.5.4'}
# Matches avif/bridge AUTO_THREADS, THREADED_MIN_PIXELS(_420) and avif/engine
# MAX_DECODE_THREADS (the explicit-request bound).
THREADS = {'default_engine': 'dav1d', 'oracle_engine': 'libaom', 'cap': 4, 'explicit_max': 8,
           'policy': 'min(usable cores, cap) for 4:2:0 frames of at least 8388608 pixels '
                     'and other frames of at least 2097152 pixels, otherwise 1',
           'libaom_multithread': False}

def run(args, **kw):
    subprocess.run([str(x) for x in args], check=True, stdout=sys.stderr, **kw)

@contextmanager
def native_lock(root):
    """Every recipe shares configure trees, dav1d staging and publication."""
    lock = root/'build/native-recipe.lock'
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield

def main():
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['artifact'])
    p.add_argument('name', choices=['native'])
    p.add_argument('--platform', required=True)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    if a.platform != 'linux-x86_64-gnu':
        p.error('supported platform: linux-x86_64-gnu; other targets unvalidated')
    if sys.platform != 'linux' or platform.machine() not in ('x86_64', 'AMD64'):
        p.error('native recipes validated only on Linux x86-64 hosts')
    root = Path(os.environ.get('ZIRAN_PACKAGE_ROOT', Path(__file__).resolve().parents[1]))
    tool = os.environ.get('ZIRAN') or str(Path(os.environ['ZIRAN_TOOLCHAIN_ROOT'])/'build/bin/ziran')
    with native_lock(root):
        build_artifact(a, root, tool)

def build_artifact(a, root, tool):
    pins = dict(PINS)
    sources = {}
    for name, expected in pins.items():
        path = Path(subprocess.check_output([tool, 'pkg', 'path', name], cwd=root, text=True).strip())
        actual = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != expected:
            raise RuntimeError(f'{name} pin mismatch: {actual} != {expected}')
        if subprocess.check_output(['git', '-C', str(path), 'status', '--porcelain'], text=True).strip():
            raise RuntimeError(f'{name} source must be clean')
        sources[name] = path
    env = os.environ.copy()
    # dav1d builds with the exact Meson/Ninja from native/requirements.txt.
    tools = root/'build/native-tools'
    if tools.is_dir():
        env['PYTHONPATH'] = str(tools)
        env['PATH'] = str(tools/'bin') + os.pathsep + env['PATH']
    version = subprocess.check_output([sys.executable, '-m', 'mesonbuild.mesonmain', '--version'], env=env, text=True).strip()
    ninja_version = subprocess.check_output(['ninja', '--version'], env=env, text=True).strip()
    if version != '1.9.1' or ninja_version not in ('1.13.0', '1.13.0.git.kitware.jobserver-pipe-1'):
        raise RuntimeError('native requires native/requirements.txt tool versions (meson 1.9.1, ninja 1.13.0)')
    build = root / ('build/' + a.name)
    run(['cmake', '-S', root/'native', '-B', build, '-DCMAKE_BUILD_TYPE=Release',
         f'-DZIRAN_AVIF_TOOLS={tools}' if tools.is_dir() else '-DZIRAN_AVIF_TOOLS=',
         '-DZIRAN_AVIF_DAV1D_JOBS=1', f'-DAVIF_SOURCE={sources["libavif"]}',
         f'-DAOM_SOURCE={sources["libaom"]}', f'-DDAV1D_SOURCE={sources["dav1d"]}'], env=env)
    for target in ('avif_static', 'avif_bridge'):
        run(['cmake', '--build', build, '--target', target, '--parallel', '1'], env=env)
    # Refuse publishing a truncated/interrupted intermediate archive, and a
    # libavif.a whose merged dav1d lacks its runtime-dispatched assembly.
    for archive in (build/'aom/libaom.a', build/'avif/libavif.a'):
        inspected = subprocess.run(['nm', '-g', archive], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if inspected.returncode or inspected.stderr:
            raise RuntimeError('invalid native archive: ' + inspected.stderr[:2000])
    symbols = subprocess.run(['nm', build/'avif/libavif.a'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True).stdout
    for tier in ('_ssse3', '_avx2', '_avx512icl'):
        if tier not in symbols:
            raise RuntimeError(f'libavif.a lacks dav1d {tier} assembly')
    destination = a.output.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # The package manager supplies an unpublished output directory. Stage every
    # file first, so configure/build/copy failures cannot truncate valid files.
    with tempfile.TemporaryDirectory(prefix='.avif-stage-', dir=destination.parent) as temporary:
        out = Path(temporary)
        stage_artifact(out, a, root, build, sources, pins)
        destination.mkdir(parents=True, exist_ok=True)
        for source in sorted(out.rglob('*')):
            relative = source.relative_to(out)
            target = destination/relative
            if source.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                os.replace(source, target)

def stage_artifact(out, a, root, build, sources, pins):
    (out/'lib').mkdir(parents=True, exist_ok=True)
    (out/'resources').mkdir(parents=True, exist_ok=True)
    shutil.copyfile(build/'libavif_bridge.so', out/'lib/libavif_bridge.so')
    # libavif.a is upstream's merged archive: libavif plus the dav1d codec.
    for name, sub in (('libavif', 'avif'), ('libaom', 'aom')):
        shutil.copyfile(build/sub/f'{name}.a', out/'lib'/f'{name}.a')
        shutil.copyfile(sources[name]/'LICENSE', out/'resources'/f'LICENSE-{name}')
    shutil.copyfile(sources['libaom']/'PATENTS', out/'resources/PATENTS-libaom')
    shutil.copyfile(sources['dav1d']/'COPYING', out/'resources/LICENSE-dav1d')
    (out/'provenance.json').write_text(json.dumps({'schema': 2, 'platform': a.platform,
        'sources': pins, 'versions': VERSIONS, 'threads': THREADS,
        'dav1d': {'asm': True, 'cpu_dispatch': 'runtime', 'merged_into': 'lib/libavif.a'},
        'encoder': False, 'libyuv': False, 'libsharpyuv': False}, indent=2)+'\n')
    (out/'link.txt').write_text('archive\tlib/libavif.a\narchive\tlib/libaom.a\n'
                                'library\t-lpthread\nlibrary\t-ldl\nlibrary\t-lm\n')

if __name__ == '__main__':
    main()
