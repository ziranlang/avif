#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
out="$root/build/scratch/avif"
mkdir -p "$out"
# Package validation is independent of the standalone module tests.
"$ziran" lock --offline >"$out/package-lock.log" 2>&1
"$ziran" check --project src/api.zi >"$out/package-check.log" 2>&1
consumer="$out/consumer"
mkdir -p "$consumer"
cat > "$consumer/ziran.toml" <<'TOML'
[package]
name = "avif-native-test"
[toolchain]
git = "https://github.com/ziranlang/ziran.git"
ref = "master"
[dependencies.avif]
git = "https://github.com/ziranlang/avif.git"
ref = "master"
TOML
av1_package=${AV1_PACKAGE_ROOT:-$("$ziran" pkg path av1)}
cat > "$consumer/ziran.local.toml" <<TOML
[overrides]
avif = "$root"
av1 = "$av1_package"
image_codec = "$foundation"
ziran = "$toolchain"
TOML
(cd "$consumer"; "$ziran" lock --offline)
native=$(cd "$consumer"; "$ziran" pkg artifact avif:native --platform linux-x86_64-gnu)
base=$(dirname "$native")
export LDLIBS="$base/lib/libavif.a $base/lib/libaom.a -lpthread -ldl -lm"
printf '%s\n' "$native" >"$out/native-artifact.txt"
# Exercise the toolchain's descriptor parser and ordered native link flags.
cat >"$out/artifact-link.c" <<'C'
extern const char *avifVersion(void);
int main(void) { return avifVersion() == 0; }
C
python3 - "$toolchain" "$native" "$out" <<'PY'
import importlib.util
from pathlib import Path
import subprocess
import sys
toolchain, descriptor, out = map(Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location('ziran_artifacts', toolchain/'scripts/ziran_artifacts.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
artifact = module.Artifact(descriptor, artifact='native', platform='linux-x86_64-gnu')
flags = artifact.link_flags()
assert flags == [str(artifact.output('lib/libavif.a')), str(artifact.output('lib/libaom.a')),
                 '-lpthread', '-ldl', '-lm'], flags
subprocess.run(['cc', str(out/'artifact-link.c'), '-o', str(out/'artifact-link'), *flags], check=True)
subprocess.run([str(out/'artifact-link')], check=True)
PY
python3 tests/native_bootstrap.py
# dav1d is the default engine; libaom is the explicit oracle. Both must pass.
AVIF_LIB_DIR="$base/lib" AVIF_ENGINE=dav1d sh tests/bridge_core.sh
AVIF_LIB_DIR="$base/lib" AVIF_ENGINE=libaom sh tests/bridge_core.sh
sh tests/abi.sh
sh tests/bridge_contract.sh
sh tests/into_contract.sh
sh tests/static_into.sh
sh tests/engine_contract.sh
sh tests/bmff.sh
sh tests/container.sh
sh tests/dynamic.sh
sh tests/native_recipe.sh
sh tests/transforms_color.sh
# Authored AV1 decode of every fixture item through the container parser,
# against the pinned libaom this package's native artifact links.
AV1_AOM_LIBRARY="${AV1_AOM_LIBRARY:-$base/lib/libaom.a}" sh tests/av1_fixtures.sh
printf '%s\n' 'AVIF package: package resolution, native recipe and core passed'
