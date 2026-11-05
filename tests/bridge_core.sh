#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
out="$root/build/scratch/avif"
mkdir -p "$out"
: "${AVIF_LIB_DIR:?native recipe library directory required}"
export LDLIBS="$AVIF_LIB_DIR/libavif.a $AVIF_LIB_DIR/libaom.a ${AVIF_EXTRA_LIBS:-} -lpthread -ldl -lm"
"$ziran" ir --root tests --module-path "avif=$root/src" --module-path "$root/src" --module-path "$root/src/bridge" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std" -o "$out/ir" tests/contracts.zi
for form in source saved; do
    input="$root/tests/contracts.zi"
    set -- --root tests --module-path "avif=$root/src" --module-path "$root/src" --module-path "$root/src/bridge" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std"
    if test "$form" = saved; then input="$out/ir/contracts.zir"; set -- --root "$out/ir" --module-path "$out/ir"; fi
    "$ziran" build --target=c --exe --entry contracts:main "$@" -o "$out/$form" "$input"
    timeout 30s "$out/$form/contracts" "$root/tests/fixtures" "${AVIF_ENGINE:-dav1d}"
done
"$ziran" build --target=c --exe --entry avif:main --root tools --module-path "avif=$root/src" --module-path "$root/src" --module-path "$root/src/bridge" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std" -o "$out/cli" tools/avif.zi
cp "$out/cli/avif" "$root/build/bin/avif"
# The CLI defaults to dav1d; the libaom oracle must stay byte-identical.
"$root/build/bin/avif" "$root/tests/fixtures/rgba8.avif" "$out/cli.rgba"
cmp "$out/cli.rgba" "$root/tests/fixtures/rgba8.strict.rgba"
"$root/build/bin/avif" "$root/tests/fixtures/rgba8.avif" "$out/cli-libaom.rgba" libaom
cmp "$out/cli-libaom.rgba" "$root/tests/fixtures/rgba8.strict.rgba"
python3 tests/verify_fixtures.py
printf '%s\n' 'AVIF core: source + saved IR, headless CLI passed'
