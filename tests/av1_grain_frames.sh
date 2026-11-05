#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
out="$root/build/scratch/av1-grain-frames"
aom=${AV1_AOM_SOURCE:-$("$ziran" pkg path libaom)}
# Reuse the same pinned, test-only encoder cache as the full-key controls.
# The production bridge recipe remains decoder-only.
encoder_library=${AV1_AOM_ENCODER_LIBRARY:-$root/build/scratch/av1-key-controls/aom/libaom.a}
if test -n "${AV1_AOM_ENCODER_LIBRARY:-}" && test ! -f "$encoder_library"; then
    printf 'Missing pinned encoder oracle: %s\n' "$encoder_library" >&2
    exit 1
fi
if test ! -f "$encoder_library"; then
    test "$(git -C "$aom" rev-parse HEAD)" = d772e334cc724105040382a977ebb10dfd393293
    git -C "$aom" diff --quiet HEAD --
    encoder_config="$root/build/scratch/av1-key-controls/aom"
    cmake -S "$aom" -B "$encoder_config" -DCMAKE_BUILD_TYPE=Release \
        -DENABLE_DOCS=0 -DENABLE_EXAMPLES=0 -DENABLE_TESTS=0 -DENABLE_TOOLS=0 \
        -DCONFIG_AV1_ENCODER=1 -DCONFIG_AV1_DECODER=1
    cmake --build "$encoder_config" --target aom --parallel 1
    encoder_library="$encoder_config/libaom.a"
fi
export AV1_AOM_ENCODER_LIBRARY="$encoder_library"
python3 tests/av1_grain_frames_oracle.py --root "$root" --out "$out" --aom "$aom"
module=av1_grain_frames_vectors
for shard in 0 1 2 3 4 5 6 7; do
group="$out/shard$shard"
printf '%s\n' "AV1 encoded grain frames shard $shard/7"
"$ziran" ir --root "$group" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std" -o "$group/ir" "$group/$module.zi"
for form in source saved; do
    input="$group/$module.zi"
    set -- --root "$group" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std"
    if test "$form" = saved; then input="$group/ir/$module.zir"; set -- --root "$group/ir" --module-path "$group/ir"; fi
    "$ziran" build --target=c --exe --entry "$module:main" "$@" -o "$group/$form" "$input"
    "$group/$form/$module"
    "$ziran" bundle --entry "$module:main" "$@" -o "$group/$form.zx" "$input"
    test "$("$toolchain/build/bin/zi2zx-vm" run "$group/$form.zx")" = 0
    "$ziran" build --target=go --pkg main --entry "$module:main" "$@" -o "$group/$form-go" "$input"
    printf 'package main\nfunc main() { if Av1GrainFramesVectors_Main() != 0 { panic("AV1 scalar complete grain noise") } }\n' > "$group/$form-go/main.go"
    (cd "$group/$form-go" && GO111MODULE=off go build -o run . && ./run)
done
CFLAGS='-O0 -g -fsanitize=address,undefined -fno-omit-frame-pointer' LDFLAGS='-fsanitize=address,undefined' \
    "$ziran" build --target=c --exe --entry "$module:main" --root "$group" \
    --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std" -o "$group/sanitized" "$group/$module.zi"
ASAN_OPTIONS=detect_leaks=1 UBSAN_OPTIONS=halt_on_error=1 "$group/sanitized/$module"
done
"$ziran" build --target=c --no-main --entry av1_grain_allocation:GrainAllocationFailure --root "$out/allocation" \
    --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std" -o "$out/allocation-c" "$out/allocation/av1_grain_allocation.zi"
cat > "$out/allocation-c/host.c" <<'C'
#include "av1_grain_allocation.h"
#include <stddef.h>
static int calls,fail_at;
void *__real_realloc(void *,size_t);
void *__wrap_realloc(void *pointer,size_t bytes) {
    calls++;if(calls==fail_at)return NULL;return __real_realloc(pointer,bytes);
}
int main(void) {
    for(fail_at=1;fail_at<=3;fail_at++){calls=0;if(GrainAllocationFailure()!=0||calls!=fail_at)return 1;}
    return 0;
}
C
"${CC:-cc}" -std=c11 -O1 -g -fno-builtin-realloc -fsanitize=address,undefined -fno-sanitize-recover=all \
    -I"$toolchain/include" -I"$out/allocation-c" "$out/allocation-c"/*.c -Wl,--wrap=realloc -lm -o "$out/allocation-c/test"
ASAN_OPTIONS=detect_leaks=1 UBSAN_OPTIONS=halt_on_error=1 "$out/allocation-c/test"
python3 - "$out" <<'PY'
import json,pathlib,sys
out=pathlib.Path(sys.argv[1]);receipt=json.loads((out/'oracle.json').read_text())
receipt.update(command='build-queue -- sh tests/av1_grain_frames.sh',exit_code=0,
    forms=['source','saved IR'],targets=['C','Go','direct zi2zx-vm'],sanitizers=['ASan','UBSan'],sanitizer_optimization='-O0',allocation_failures=[1,2,3])
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
PY
printf '%s\n' 'AV1 encoded grain frames: pinned pictures, source/saved C/Go/directVM + ASan/UBSan passed'
