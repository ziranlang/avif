#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
out="$root/build/scratch/container"
mkdir -p "$out"
python3 tests/malformed_container.py
"$ziran" ir --root tests --module-path "$root/src" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std" -o "$out/ir" tests/container_contract.zi
for form in source saved; do
    input="$root/tests/container_contract.zi"
    set -- --root tests --module-path "$root/src" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std"
    if test "$form" = saved; then input="$out/ir/container_contract.zir"; set -- --root "$out/ir" --module-path "$out/ir"; fi
    "$ziran" build --target=c --exe --entry container_contract:main "$@" -o "$out/$form" "$input"
    timeout 30s "$out/$form/container_contract" "$root/tests/fixtures" "$out/malformed"
done
