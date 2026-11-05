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
cat > "$consumer/ziran.local.toml" <<TOML
[overrides]
avif = "$root"
image_codec = "$foundation"
ziran = "$toolchain"
TOML
(cd "$consumer"; "$ziran" lock --offline)
native=$(cd "$consumer"; "$ziran" pkg artifact avif:native --platform linux-x86_64-gnu)
base=$(dirname "$native")
export LDLIBS="$base/lib/libavif.a $base/lib/libaom.a -lpthread -ldl -lm"
printf '%s\n' "$native" >"$out/native-artifact.txt"
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
printf '%s\n' 'AVIF package: package resolution, native recipe and core passed'
