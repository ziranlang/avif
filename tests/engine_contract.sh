#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
out="$root/build/scratch/engine-contract"
mkdir -p "$out"
"$ziran" ir --root tests --module-path "avif=$root/src" --module-path "$root/src" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std" -o "$out/ir" tests/engine_contract.zi
for form in source saved; do
    input="$root/tests/engine_contract.zi"
    set -- --root tests --module-path "avif=$root/src" --module-path "$root/src" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std"
    if test "$form" = saved; then input="$out/ir/engine_contract.zir"; set -- --root "$out/ir" --module-path "$out/ir"; fi
    "$ziran" build --target=c --exe --entry engine_contract:main "$@" -o "$out/$form" "$input"
    "$out/$form/engine_contract"
    "$ziran" bundle --entry engine_contract:main "$@" -o "$out/$form.zx" "$input"
    test "$("$ziran" run "$out/$form.zx")" = 0
    test "$("$toolchain/build/bin/zi2zx" run --vm "$out/$form.zx")" = 0
done
printf '%s\n' 'AVIF fake-engine contracts: source/saved IR native C and explicit portable VM passed'
