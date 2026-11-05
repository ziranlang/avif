#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
out="$root/build/scratch/bmff"
mkdir -p "$out"
"$ziran" ir --root tests --module-path "avif=$root/src" --module-path "$root/src" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std" -o "$out/ir" tests/bmff_contract.zi
for form in source saved; do
    input="$root/tests/bmff_contract.zi"
    set -- --root tests --module-path "avif=$root/src" --module-path "$root/src" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std"
    if test "$form" = saved; then input="$out/ir/bmff_contract.zir"; set -- --root "$out/ir" --module-path "$out/ir"; fi
    "$ziran" build --target=c --exe --entry bmff_contract:main "$@" -o "$out/$form" "$input"
    "$out/$form/bmff_contract"
    "$ziran" bundle --entry bmff_contract:main "$@" -o "$out/$form.zx" "$input"
    test "$("$ziran" run "$out/$form.zx")" = 0
    test "$("$toolchain/build/bin/zi2zx-vm" run "$out/$form.zx")" = 0
done
