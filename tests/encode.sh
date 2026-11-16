#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
artifact=$(cat "$root/build/scratch/avif/native-artifact.txt")
base=$(dirname "$artifact")
export LDLIBS="$base/lib/libavif.a $base/lib/libaom.a -lpthread -ldl -lm"
out="$root/build/scratch/encode"
mkdir -p "$out"
"$ziran" ir --root tests --module-path "$root/src" --module-path "$root/src/bridge" --module-path "avif=$root/src" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std" -o "$out/ir" tests/encode_roundtrip.zi
for form in source saved; do
    input="$root/tests/encode_roundtrip.zi"
    set -- --root tests --module-path "$root/src" --module-path "$root/src/bridge" --module-path "avif=$root/src" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std"
    if test "$form" = saved; then input="$out/ir/encode_roundtrip.zir"; set -- --root "$out/ir" --module-path "$out/ir"; fi
    "$ziran" build --target=c --exe --entry encode_roundtrip:main "$@" -o "$out/$form" "$input"
    timeout 120s "$out/$form/encode_roundtrip" "$out"
done
