"""Exercise the project-tool entry point without preinstalled native tools."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def main():
    tools = ROOT/'build/native-tools'
    backup = ROOT/'backup'
    backup.mkdir(exist_ok=True)
    env = os.environ.copy()
    for name in ('PYTHONPATH', 'PYTHONHOME', 'ZIRAN_AVIF_TOOLS'):
        env.pop(name, None)
    # Keep the real package root and stable project tool. Preserve any tools
    # another local consumer had already prepared, even if bootstrap fails.
    with tempfile.TemporaryDirectory(prefix='native-bootstrap-', dir=backup) as saved:
        previous = Path(saved)/'native-tools'
        if tools.exists():
            tools.rename(previous)
        try:
            subprocess.run(['make', 'build/bin/avif-native'], cwd=ROOT, env=env, check=True)
            assert (tools/'mesonbuild').is_dir(), 'project tool did not bootstrap Meson'
            assert (tools/'ninja').is_dir(), 'project tool did not bootstrap Ninja'
            env['PYTHONPATH'] = str(tools)
            assert subprocess.check_output(
                [sys.executable, '-m', 'mesonbuild.mesonmain', '--version'],
                env=env, text=True).strip() == '1.9.1'
            ninja_version = subprocess.check_output(
                [tools/'bin/ninja', '--version'], env=env, text=True).strip()
            assert ninja_version in ('1.13.0', '1.13.0.git.kitware.jobserver-pipe-1')
            # A warm invocation must not reinstall tools or rewrite the provider.
            subprocess.run(['make', '--question', 'build/bin/avif-native'],
                           cwd=ROOT, env=env, check=True)
        finally:
            if previous.exists():
                if tools.exists():
                    shutil.rmtree(tools)
                previous.rename(tools)
    print('Native bootstrap: absent tools installed at pinned versions; warm build reused; prior tools preserved')


if __name__ == '__main__':
    main()
