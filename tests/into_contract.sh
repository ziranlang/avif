#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
out="$root/build/scratch/into-contract"
mkdir -p "$out"
"${CC:-cc}" -c tests/scratch_alloc.c -o "$out/scratch_alloc.o"
"$ziran" ir --root tests --module-path "avif=$root/src" --module-path "$root/src" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std" -o "$out/ir" tests/into_contract.zi
for form in source saved; do
    input="$root/tests/into_contract.zi"
    set -- --root tests --module-path "avif=$root/src" --module-path "$root/src" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std"
    if test "$form" = saved; then input="$out/ir/into_contract.zir"; set -- --root "$out/ir" --module-path "$out/ir"; fi
    LDLIBS="$out/scratch_alloc.o -Wl,--wrap=realloc,--wrap=malloc,--wrap=calloc" "$ziran" build --target=c --exe --entry into_contract:main "$@" -o "$out/$form" "$input"
    "$out/$form/into_contract"
    if nm -u "$out/$form/into_contract" | rg -q 'avif|aom'; then exit 1; fi
done
printf '%s\n' 'Caller-output contract source/saved IR: direct pointer, zero scratch, padded rows, bounded transforms and failure/cancellation metadata passed'
