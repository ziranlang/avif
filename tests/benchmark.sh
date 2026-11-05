#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
artifact=$(cat "$root/build/scratch/avif/dav1d-artifact.txt")
base=$(dirname "$artifact")
out="$root/build/scratch/benchmark"
mkdir -p "$out"
export LDLIBS="$base/lib/libavif.a $base/lib/libaom.a $base/lib/libdav1d.a -lpthread -ldl -lm"
"$ziran" build --target=c --exe --entry bench:main --root tools --module-path "avif=$root/src" --module-path "$root/src" --module-path "$root/src/bridge" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std" -o "$out" tools/bench.zi
cp "$out/bench" "$root/build/bin/avif-bench"
python3 tests/benchmark.py --input tests/fixtures/rgba8.avif --expected tests/fixtures/rgba8.strict.rgba --output build/reports/tiny-comparison.json
if test -n "${AVIF_LOCAL_INPUT:-}"; then
    "$root/build/bin/avif" "$AVIF_LOCAL_INPUT" "$out/local.rgba" aom
    python3 tests/benchmark.py --input "$AVIF_LOCAL_INPUT" --expected "$out/local.rgba" --local-only --output build/reports/local-comparison.json
fi
