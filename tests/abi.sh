#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
out="$root/build/scratch/abi"
python3 tests/abi.py
headers=$("$ziran" pkg path libavif)
"${CC:-cc}" -std=c11 -I"$headers/include" "$out/native.c" -o "$out/native"
"$out/native" >"$out/native.txt"
"$ziran" ir --root "$out" --module-path "avif=$root/src" --module-path "$root/src" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std" -o "$out/ir" "$out/abi_contract.zi"
for form in source saved; do
    input="$out/abi_contract.zi"
    set -- --root "$out" --module-path "avif=$root/src" --module-path "$root/src" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std"
    if test "$form" = saved; then input="$out/ir/abi_contract.zir"; set -- --root "$out/ir" --module-path "$out/ir"; fi
    LDLIBS= "$ziran" build --target=c --exe --entry abi_contract:main "$@" -o "$out/$form" "$input"
    "$out/$form/abi_contract" >"$out/$form.txt"
    cmp "$out/native.txt" "$out/$form.txt"
done
printf '%s\n' 'Pinned libavif1.3 ABI sizeof/offsetof: every declared bridge field matched source/saved IR (decoder is an intentional prefix)'
