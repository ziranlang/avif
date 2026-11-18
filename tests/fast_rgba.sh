#!/bin/sh
# The native bridge's fast 8-bit RGBA conversion against the scalar reference.
set -eu
. "$(dirname -- "$0")/common.sh"
out="$root/build/scratch/fast-rgba"
mkdir -p "$out"
set -- --root tests --module-path "$root/src" \
    --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std"
for threads in single posix; do
    defines=""
    if test "$threads" = posix; then defines="--define POSIX_THREADS"; fi
    LDLIBS=-lpthread "$ziran" build --target=c --exe $defines --entry fast_rgba_contract:main "$@" \
        -o "$out/$threads-c" tests/fast_rgba_contract.zi
    "$out/$threads-c/fast_rgba_contract"
done
