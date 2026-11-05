"""Real static include/link/run plus shared recipe concurrency/failure tests."""
from importlib.util import module_from_spec, spec_from_file_location
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT/'build/scratch/native-recipe'

def run(arguments, name, success=True):
    log = OUT/(name+'.log')
    with log.open('w') as stream:
        result = subprocess.run([str(x) for x in arguments], stdout=stream, stderr=subprocess.STDOUT)
    if (result.returncode == 0) != success:
        with log.open('rb') as stream:
            stream.seek(max(0, log.stat().st_size-6000))
            sys.stderr.write(stream.read(6000).decode(errors='replace'))
        raise AssertionError(f'{name}: exit {result.returncode}, log {log}')

def load_provider():
    spec = spec_from_file_location('avif_native_provider', ROOT/'native/provider.py')
    provider = module_from_spec(spec)
    spec.loader.exec_module(provider)
    return provider

def lock_worker(root, ready, acquired, release):
    provider = load_provider()
    ready.set()
    with provider.native_lock(root):
        acquired.set()
        release.wait(15)

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tool = os.environ['ZIRAN']
    paths = {name: subprocess.check_output([tool,'pkg','path',name], cwd=ROOT, text=True).strip()
             for name in ('libavif','libaom','dav1d')}
    project = OUT/'consumer'
    project.mkdir(exist_ok=True)
    (project/'CMakeLists.txt').write_text('''cmake_minimum_required(VERSION 3.17)
project(avif_consumer C CXX ASM)
include("${AVIF_PACKAGE}/native/ZiranAvif.cmake")
ziran_avif_add_native(AVIF_SOURCE "${AVIF_SOURCE}" AOM_SOURCE "${AOM_SOURCE}" DAV1D_SOURCE "${DAV1D_SOURCE}")
# Idempotent repeated inclusion must not duplicate the codec targets.
ziran_avif_add_native(AVIF_SOURCE "${AVIF_SOURCE}" AOM_SOURCE "${AOM_SOURCE}" DAV1D_SOURCE "${DAV1D_SOURCE}")
add_executable(native_consumer "${AVIF_PACKAGE}/tests/native_consumer.c")
target_link_libraries(native_consumer PRIVATE ziran_avif::static)
''')
    build = OUT/'consumer-build'
    run(['cmake','-S',project,'-B',build,'-DCMAKE_BUILD_TYPE=Release',f'-DAVIF_PACKAGE={ROOT}',
         f'-DAVIF_SOURCE={paths["libavif"]}',f'-DAOM_SOURCE={paths["libaom"]}',
         f'-DDAV1D_SOURCE={paths["dav1d"]}','-DZIRAN_AVIF_DAV1D_JOBS=1'],'consumer-configure')
    cache = (build/'CMakeCache.txt').read_text().splitlines()
    for setting in ('CONFIG_AV1_ENCODER:BOOL=0','CONFIG_AV1_DECODER:BOOL=1','CONFIG_MULTITHREAD:BOOL=0',
                    'AVIF_CODEC_AOM_ENCODE:BOOL=OFF','AVIF_CODEC_AOM_DECODE:BOOL=ON',
                    'AVIF_CODEC_DAV1D:STRING=SYSTEM','AVIF_LIBYUV:STRING=OFF'):
        assert setting in cache, setting
    run(['cmake','--build',build,'--target','native_consumer','--parallel','1'],'consumer-build')
    run([build/'native_consumer',ROOT/'tests/fixtures/rgba8.avif',ROOT/'tests/fixtures/rgba8.strict.rgba'],'consumer-run')
    # A caller cannot silently substitute an arbitrary upstream revision.
    bad = OUT/'bad-pin'
    bad.mkdir(exist_ok=True)
    (bad/'CMakeLists.txt').write_text('''cmake_minimum_required(VERSION 3.16)
project(avif_bad_pin NONE)
include("${AVIF_PACKAGE}/native/ZiranAvif.cmake")
find_package(Git REQUIRED)
_ziran_avif_source(libavif "${AVIF_SOURCE}" 0000000000000000000000000000000000000000 include/avif/avif.h)
''')
    run(['cmake','-S',bad,'-B',OUT/'bad-pin-build',f'-DAVIF_PACKAGE={ROOT}',f'-DAVIF_SOURCE={paths["libavif"]}'],
        'reject-wrong-pin',success=False)
    assert 'source pin mismatch' in (OUT/'reject-wrong-pin.log').read_text()
    # Hold the same real recipe lock used for configure/build/stage. A second
    # independent process must wait until the first has fully left its scope.
    ctx = multiprocessing.get_context('spawn')
    events = [ctx.Event() for _ in range(6)]
    first = ctx.Process(target=lock_worker,args=(ROOT,*events[:3]))
    second = ctx.Process(target=lock_worker,args=(ROOT,*events[3:]))
    try:
        first.start(); assert events[0].wait(10) and events[1].wait(10)
        second.start(); assert events[3].wait(10)
        assert not events[4].wait(0.2), 'recipe lock allowed overlapping consumers'
        events[2].set(); assert events[4].wait(10)
        events[5].set(); first.join(10); second.join(10)
        assert first.exitcode == second.exitcode == 0
    finally:
        events[2].set(); events[5].set()
        for process in (first, second):
            if process.pid and process.is_alive():
                process.terminate(); process.join()
    # A staging failure never starts replacing a consumer's valid artifacts.
    # Use real valid warm archives, then force a missing required license.
    provider = load_provider()
    class Arguments:
        name = 'native'
        platform = 'linux-x86_64-gnu'
        output = OUT/'preserved-output'
    Arguments.output.mkdir(exist_ok=True)
    sentinel = Arguments.output/'provenance.json'
    sentinel.write_text('preserve existing valid output\n')
    real_copy = provider.shutil.copyfile
    def fail_license(source, target):
        if Path(source).name == 'LICENSE':
            raise OSError('injected missing license')
        return real_copy(source, target)
    with patch.object(provider, 'run'), patch.object(provider.shutil, 'copyfile', side_effect=fail_license):
        try:
            provider.build_artifact(Arguments, ROOT, tool)
            raise AssertionError('missing license accepted')
        except OSError as error:
            assert 'injected missing license' in str(error)
    assert sentinel.read_text() == 'preserve existing valid output\n'
    assert not (Arguments.output/'lib').exists()
    print('Native recipe: reusable static include/link/exact golden, pinned flags, wrong-pin rejection, shared lock and failed-stage preservation passed')

if __name__ == '__main__':
    main()
