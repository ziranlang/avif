#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
artifact=$(cat "$root/build/scratch/avif/native-artifact.txt")
base=$(dirname "$artifact")
export LDLIBS="$base/lib/libavif.a $base/lib/libaom.a -lm"
out="$root/build/scratch/static-into"
mkdir -p "$out"
"$ziran" ir --root tests --module-path "$root/src" --module-path "$root/src/bridge" --module-path "avif=$root/src" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std" -o "$out/ir" tests/static_into.zi
for form in source saved; do
    input="$root/tests/static_into.zi"
    set -- --root tests --module-path "$root/src" --module-path "$root/src/bridge" --module-path "avif=$root/src" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std"
    if test "$form" = saved; then input="$out/ir/static_into.zir"; set -- --root "$out/ir" --module-path "$out/ir"; fi
    "$ziran" build --target=c --exe --entry static_into:main "$@" -o "$out/$form" "$input"
    timeout 30s "$out/$form/static_into" "$root/tests/fixtures"
done
