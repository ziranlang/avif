#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
out="$root/build/scratch/av1-lossless"
aom=${AV1_AOM_SOURCE:-$("$ziran" pkg path libaom)}
python3 tests/av1_lossless_oracle.py --root "$root" --out "$out" --aom "$aom"
python3 tests/av1_coefficient_edges.py --root "$root" --out "$out" --aom "$aom"
for module in av1_lossless_vectors av1_coefficient_edges; do
    suite="$out/$module"
    "$ziran" ir --root "$out" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std" -o "$suite/ir" "$out/$module.zi"
    for form in source saved; do
        input="$out/$module.zi"
        set -- --root "$out" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std"
        if test "$form" = saved; then input="$suite/ir/$module.zir"; set -- --root "$suite/ir" --module-path "$suite/ir"; fi
        "$ziran" build --target=c --exe --entry "$module:main" "$@" -o "$suite/$form" "$input"
        "$suite/$form/$module"
        "$ziran" bundle --entry "$module:main" "$@" -o "$suite/$form.zx" "$input"
        test "$("$toolchain/build/bin/zi2zx-vm" run "$suite/$form.zx")" = 0
        "$ziran" build --target=go --pkg main --entry "$module:main" "$@" -o "$suite/$form-go" "$input"
        entry=$(python3 -c 'import sys; print("".join(x.capitalize() for x in sys.argv[1].split("_")) + "_Main")' "$module")
        printf 'package main\nfunc main() { if %s() != 0 { panic("AV1 lossless coefficient plane parity") } }\n' "$entry" > "$suite/$form-go/main.go"
        (cd "$suite/$form-go" && GO111MODULE=off go build -o run . && ./run)
    done
    CFLAGS='-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer' LDFLAGS='-fsanitize=address,undefined' \
        "$ziran" build --target=c --exe --entry "$module:main" --root "$out" \
        --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std" -o "$suite/sanitized" "$out/$module.zi"
    ASAN_OPTIONS=detect_leaks=1 UBSAN_OPTIONS=halt_on_error=1 "$suite/sanitized/$module"
done
python3 - "$out" <<'PY'
import json,pathlib,sys
out=pathlib.Path(sys.argv[1]);oracle=json.loads((out/'oracle.json').read_text())
supported=[case for case in oracle['cases'] if case['supported']]
receipt=dict(command='build-queue -- sh tests/av1_coefficients.sh',exit_code=0,
    oracle_revision=oracle['revision'],oracle_library_sha256=oracle['library_sha256'],
    encoder=oracle['encoder'],real_lossless_inputs=len(oracle['cases']),decoded_planes=len(supported),
    unsupported_modes=len(oracle['cases'])-len(supported),invalid_prefixes=sum(len(case['data']) for case in supported),
    entropy_fuzz_cases=512,depths=[8,10,12],forms=['source','saved IR'],targets=['C','Go','direct zi2zx-vm'],
    sanitizers=['ASan','UBSan'],boundaries=json.loads((out/'edge_oracle.json').read_text()),
    scope='lossless8x8 monochrome implemented intra block; general AV1 decode pending')
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
PY
printf '%s\n' 'AV1 lossless4x4 coefficients/WHT/intra8x8: pinned native planes, source/saved C/Go/directVM + ASan/UBSan passed; broader AV1 pending'
