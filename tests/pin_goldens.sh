#!/bin/sh
# Explicit golden regeneration only, never called by avif.sh.
set -eu
. "$(dirname -- "$0")/common.sh"
: "${KRYON_ROOT:?canonical Kryon working copy required}"
baseline="$KRYON_ROOT/backup/codec-extraction-baseline"
(cd "$baseline"; printf '%s\n' 'b9d08b0c74864509fbfac89bec6ef58524067cd932b6c5541c4fba2f94cf50a8  avif_decode.zi' '0e866ce846825f77f7fbb6122f997cc3fb872ddba42ef5b29c229404bc266d2a  avif_image.zi' | sha256sum -c -)
libs="$KRYON_ROOT/build/avif-ziran"
out="$root/build/scratch/golden"
mkdir -p "$out"
LDLIBS="$libs/avif/libavif.a $libs/aom/libaom.a -lm" "$ziran" build --target=c --exe --entry pin_current:main --root tests --module-path "$baseline" --module-path "std=$toolchain/std" -o "$out" tests/pin_current.zi
for name in rgba8 rgba10 rgba12 gray8 gray10 gray12 transform00 transform01 transform10 transform11 transform20 transform21 transform30 transform31 premultiplied opaque animated; do
    "$out/pin_current" "$root/tests/fixtures/$name.avif" "$root/tests/fixtures/$name.strict.rgba"
done
sha256sum "$baseline/avif_decode.zi" "$baseline/avif_image.zi" "$libs/avif/libavif.a" "$libs/aom/libaom.a" > "$root/tests/fixtures/baseline.sha256"
