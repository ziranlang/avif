#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
out="$root/build/scratch/av1-key-controls"
aom=${AV1_AOM_SOURCE:-$("$ziran" pkg path libaom)}
# The bridge's reference archive is decoder-only. This extra encoder is an
# isolated test oracle, built from that same verified package source pin.
encoder_library=${AV1_AOM_ENCODER_LIBRARY:-$out/aom/libaom.a}
if test ! -f "$encoder_library"; then
    test "$(git -C "$aom" rev-parse HEAD)" = d772e334cc724105040382a977ebb10dfd393293
    git -C "$aom" diff --quiet HEAD --
    cmake -S "$aom" -B "$out/aom" -DCMAKE_BUILD_TYPE=Release \
        -DENABLE_DOCS=0 -DENABLE_EXAMPLES=0 -DENABLE_TESTS=0 -DENABLE_TOOLS=0 \
        -DCONFIG_AV1_ENCODER=1 -DCONFIG_AV1_DECODER=1
    cmake --build "$out/aom" --target aom --parallel 1
fi
export AV1_AOM_ENCODER_LIBRARY="$encoder_library"
python3 tests/av1_key_controls.py --root "$root" --out "$out" --aom "$aom"
module=av1_key_controls_vectors
"$ziran" ir --root "$out" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std" -o "$out/ir" "$out/$module.zi"
for form in source saved; do
    input="$out/$module.zi"
    set -- --root "$out" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std"
    if test "$form" = saved; then input="$out/ir/$module.zir"; set -- --root "$out/ir" --module-path "$out/ir"; fi
    "$ziran" build --target=c --exe --entry "$module:main" "$@" -o "$out/$form" "$input"
    "$out/$form/$module"
    "$ziran" bundle --entry "$module:main" "$@" -o "$out/$form.zx" "$input"
    test "$("$toolchain/build/bin/zi2zx-vm" run "$out/$form.zx")" = 0
    "$ziran" build --target=go --pkg main --entry "$module:main" "$@" -o "$out/$form-go" "$input"
    printf 'package main\nfunc main() { if Av1KeyControlsVectors_Main() != 0 { panic("AV1 full key controls") } }\n' > "$out/$form-go/main.go"
    (cd "$out/$form-go" && GO111MODULE=off go build -o run . && ./run)
done
CFLAGS='-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer' LDFLAGS='-fsanitize=address,undefined' \
    "$ziran" build --target=c --exe --entry "$module:main" --root "$out" \
    --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std" -o "$out/sanitized" "$out/$module.zi"
ASAN_OPTIONS=detect_leaks=1 UBSAN_OPTIONS=halt_on_error=1 "$out/sanitized/$module"
python3 - "$out" <<'PY'
import json,pathlib,sys
out=pathlib.Path(sys.argv[1]);receipt=json.loads((out/'oracle.json').read_text())
receipt.update(command='build-queue -- sh tests/av1_key_controls.sh',exit_code=0,
    forms=['source','saved IR'],targets=['C','Go','direct zi2zx-vm'],sanitizers=['ASan','UBSan'])
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
PY
printf '%s\n' 'AV1 full-key size/timing controls: pinned native headers/planes, source/saved C/Go/directVM + ASan/UBSan passed'
