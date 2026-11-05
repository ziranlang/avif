#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
artifact=$(cat "$root/build/scratch/avif/native-artifact.txt")
base=$(dirname "$artifact")
out="$root/build/scratch/dynamic"
mkdir -p "$out"
export LDLIBS=-ldl
"$ziran" ir --root tests --module-path "avif=$root/src" --module-path "$root/src" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std" -o "$out/ir" tests/dynamic.zi
for form in source saved; do
    input="$root/tests/dynamic.zi"
    set -- --root tests --module-path "avif=$root/src" --module-path "$root/src" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std"
    if test "$form" = saved; then input="$out/ir/dynamic.zir"; set -- --root "$out/ir" --module-path "$out/ir"; fi
    "$ziran" build --target=c --exe --entry dynamic:main "$@" -o "$out/$form" "$input"
    if nm -u "$out/$form/dynamic" | rg -q 'avif|aom'; then printf '%s\n' 'unexpected static codec reference' >&2; exit 1; fi
    timeout 30s "$out/$form/dynamic" "$base/lib/libavif_bridge.so" "$root/tests/fixtures"
done
