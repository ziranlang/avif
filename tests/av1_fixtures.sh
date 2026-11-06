#!/bin/sh
# Authored AV1 decode of the real AVIF fixtures through avif's container
# parser, against pinned libaom. Run through build-queue.
set -eu
. "$(dirname -- "$0")/common.sh"
out="$root/build/scratch/av1-fixtures"
mkdir -p "$out"
av1=${AV1_PACKAGE_ROOT:-$("$ziran" pkg path av1)}
aom=${AV1_AOM_SOURCE:-$("$ziran" pkg path libaom)}
# Test-only oracle library: the av1 package's pinned libaom build, made there
# by its tests/common.sh when missing.
library=${AV1_AOM_LIBRARY:-$av1/build/native/aom/libaom.a}
if test ! -f "$library"; then
    printf 'Missing pinned libaom oracle %s; run sh tests/av1_obu_range.sh in the av1 package first\n' "$library" >&2
    exit 1
fi
python3 tests/av1_fixtures_oracle.py --root "$root" --av1 "$av1" --out "$out" --aom "$aom" --library "$library"
module=av1_fixtures_vectors
"$ziran" ir --root "$out" --module-path "$root/src" --module-path "av1=$av1/src" --module-path "image_codec=$foundation/src" \
    --module-path "std=$toolchain/std" -o "$out/ir" "$out/$module.zi"
for form in source saved; do
    input="$out/$module.zi"
    set -- --root "$out" --module-path "$root/src" --module-path "av1=$av1/src" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std"
    if test "$form" = saved; then input="$out/ir/$module.zir"; set -- --root "$out/ir" --module-path "$out/ir"; fi
    "$ziran" build --target=go --pkg main --entry "$module:main" "$@" -o "$out/$form-go" "$input"
    printf 'package main\nfunc main() { if r := Av1FixturesVectors_Run(); r != 0 { panic(r) } }\n' > "$out/$form-go/main.go"
    (cd "$out/$form-go" && GO111MODULE=off go build -o run . && ./run)
    "$ziran" build --target=c --exe --entry "$module:main" "$@" -o "$out/$form" "$input"
    "$out/$form/$module"
    "$ziran" bundle --entry "$module:main" "$@" -o "$out/$form.zx" "$input"
    test "$("$toolchain/build/bin/zi2zx-vm" run "$out/$form.zx")" = 0
done
CFLAGS='-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer' LDFLAGS='-fsanitize=address,undefined' \
    "$ziran" build --target=c --exe --entry "$module:main" --root "$out" --module-path "$root/src" --module-path "av1=$av1/src" \
    --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std" -o "$out/sanitized" "$out/$module.zi"
ASAN_OPTIONS=detect_leaks=1 UBSAN_OPTIONS=halt_on_error=1 "$out/sanitized/$module"
python3 - "$out" <<'PY'
import json,pathlib,sys
out=pathlib.Path(sys.argv[1]);receipt=json.loads((out/'oracle.json').read_text())
receipt.update(command='build-queue -- sh tests/av1_fixtures.sh',exit_code=0,
    forms=['source','saved IR'],targets=['Go','C','direct zi2zx-vm'],sanitizers=['ASan','UBSan'])
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
PY
printf '%s\n' 'AVIF fixtures: authored AV1 decode of every color/alpha item through ParseAvif/ExtractItem matches pinned libaom, source/saved Go/C/directVM + ASan/UBSan passed'
