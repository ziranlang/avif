#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
out="$root/build/scratch/preview"
mkdir -p "$out"
"$ziran" ir --root tests --module-path "avif=$root/src" --module-path "$root/src" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std" -o "$out/ir" tests/preview_contract.zi
for form in source saved; do
    input="$root/tests/preview_contract.zi"
    set -- --root tests --module-path "avif=$root/src" --module-path "$root/src" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std"
    if test "$form" = saved; then input="$out/ir/preview_contract.zir"; set -- --root "$out/ir" --module-path "$out/ir"; fi
    LDLIBS= "$ziran" build --target=c --exe --entry preview_contract:main "$@" -o "$out/$form" "$input"
    "$out/$form/preview_contract" "$out"
    python3 tests/preview_reference.py "$out"
    portable="$root/tests/preview_portable.zi"
    set -- --root tests --module-path "avif=$root/src" --module-path "$root/src" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std"
    if test "$form" = saved; then
        "$ziran" ir "$@" -o "$out/portable-ir" "$portable"
        portable="$out/portable-ir/preview_portable.zir"
        set -- --root "$out/portable-ir" --module-path "$out/portable-ir"
    fi
    "$ziran" bundle --entry preview_portable:main "$@" -o "$out/$form.zx" "$portable"
    test "$("$ziran" run "$out/$form.zx")" = 0
    test "$("$toolchain/build/bin/zi2zx" run --backend engine "$out/$form.zx")" = 0
done
