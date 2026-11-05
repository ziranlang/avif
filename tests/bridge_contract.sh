#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
out="$root/build/scratch/bridge-contract"
mkdir -p "$out"
"$ziran" ir --root tests --module-path "avif=$root/src" --module-path "$root/src" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std" -o "$out/ir" tests/bridge_contract.zi
for form in source saved; do
    input="$root/tests/bridge_contract.zi"
    set -- --root tests --module-path "avif=$root/src" --module-path "$root/src" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std"
    if test "$form" = saved; then input="$out/ir/bridge_contract.zir"; set -- --root "$out/ir" --module-path "$out/ir"; fi
    LDLIBS= "$ziran" build --target=c --exe --entry bridge_contract:main "$@" -o "$out/$form" "$input"
    "$out/$form/bridge_contract"
    if nm -u "$out/$form/bridge_contract" | rg -q 'avif|aom'; then exit 1; fi
done
printf '%s\n' 'Function-table contract source/saved IR: no codec links, missing slots and ABI reject before Create passed'
