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
        'libaom': 'd772e334cc724105040382a977ebb10dfd393293'}
DAV1D_PIN = '54706fc6bc0cdecab7e9593974a4039cc038fca7'

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
    p.add_argument('name', choices=['native', 'native-dav1d'])
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
    if a.name == "native-dav1d": pins["dav1d"] = DAV1D_PIN
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
    extra = []
    if a.name == 'native-dav1d':
        tools = root/'build/native-tools'
        if tools.is_dir():
            env['PYTHONPATH'] = str(tools)
            env['PATH'] = str(tools/'bin') + os.pathsep + env['PATH']
        version = subprocess.check_output([sys.executable, '-m', 'mesonbuild.mesonmain', '--version'], env=env, text=True).strip()
        ninja_version = subprocess.check_output(['ninja', '--version'], env=env, text=True).strip()
        if version != '1.9.1' or ninja_version not in ('1.13.0', '1.13.0.git.kitware.jobserver-pipe-1'):
            raise RuntimeError('native-dav1d requires native/requirements.txt tool versions')
        davbuild = root/'build/native-dav1d-engine'
        prefix = root/'build/native-dav1d-install'
        meson = [sys.executable, '-m', 'mesonbuild.mesonmain']
        run(meson + ['setup', '--reconfigure', davbuild, sources['dav1d'], '--prefix', prefix,
            '--libdir=lib', '--buildtype=release', '--default-library=static', '-Denable_tools=false',
            '-Denable_tests=false', '-Denable_examples=false'], env=env)
        run(meson + ['compile', '-C', davbuild, '-j', '1'], env=env)
        run(meson + ['install', '-C', davbuild, '--no-rebuild'], env=env)
        env['PKG_CONFIG_PATH'] = str(prefix/'lib/pkgconfig')
        extra = ['-DWITH_DAV1D=ON', f'-DDAV1D_SOURCE={sources["dav1d"]}']
    build = root / ('build/' + a.name)
    run(['cmake', '-S', root/'native', '-B', build, '-DCMAKE_BUILD_TYPE=Release',
         f'-DAVIF_SOURCE={sources["libavif"]}', f'-DAOM_SOURCE={sources["libaom"]}'] + extra, env=env)
    for target in ('avif_static', 'avif_bridge'):
        run(['cmake', '--build', build, '--target', target, '--parallel', '1'], env=env)
    # Refuse publishing a truncated/interrupted intermediate archive.
    inspected = subprocess.run(['nm', '-g', build/'aom/libaom.a'], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if inspected.returncode or inspected.stderr:
        raise RuntimeError('invalid native archive: ' + inspected.stderr[:2000])
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
    for name in PINS:
        sub = 'avif' if name == 'libavif' else 'aom'
        shutil.copyfile(build/sub/f'{name}.a', out/'lib'/f'{name}.a')
        shutil.copyfile(sources[name]/'LICENSE', out/'resources'/f'LICENSE-{name}')
    shutil.copyfile(sources['libaom']/'PATENTS', out/'resources/PATENTS-libaom')
    if a.name == 'native-dav1d':
        shutil.copyfile(root/'build/native-dav1d-install/lib/libdav1d.a', out/'lib/libdav1d.a')
        shutil.copyfile(sources['dav1d']/'COPYING', out/'resources/LICENSE-dav1d')
    (out/'provenance.json').write_text(json.dumps({'schema': 1, 'platform': a.platform,
        'sources': pins, 'versions': {'libavif': '1.3.0', 'libaom': '3.13.1', **({'dav1d': '1.5.4'} if a.name == 'native-dav1d' else {})},
        'threads': 1, 'encoder': False, 'libyuv': False, 'libsharpyuv': False}, indent=2)+'\n')
    (out/'link.txt').write_text('lib/libavif.a\nlib/libaom.a\n' + ('lib/libdav1d.a\n-lpthread\n-ldl\n' if a.name == 'native-dav1d' else '') + '-lm\n')

if __name__ == '__main__':
    main()
