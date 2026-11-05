#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
out="$root/build/scratch/av1-reconstruction"
"$ziran" ir --root tests --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std" -o "$out/ir" tests/av1_reconstruction.zi
for form in source saved; do
    input="$root/tests/av1_reconstruction.zi"
    set -- --root tests --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std"
    if test "$form" = saved; then input="$out/ir/av1_reconstruction.zir"; set -- --root "$out/ir" --module-path "$out/ir"; fi
    "$ziran" build --target=c --exe --entry av1_reconstruction:main "$@" -o "$out/$form" "$input"
    "$out/$form/av1_reconstruction"
    "$ziran" bundle --entry av1_reconstruction:main "$@" -o "$out/$form.zx" "$input"
    test "$("$toolchain/build/bin/zi2zx-vm" run "$out/$form.zx")" = 0
    "$ziran" build --target=go --pkg main --entry av1_reconstruction:main "$@" -o "$out/$form-go" "$input"
    printf 'package main\nfunc main() { if Av1Reconstruction_Main() != 0 { panic("AV1 scalar DC bounds") } }\n' > "$out/$form-go/main.go"
    (cd "$out/$form-go" && GO111MODULE=off go build -o run . && ./run)
done
CFLAGS='-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer' LDFLAGS='-fsanitize=address,undefined' \
    "$ziran" build --target=c --exe --entry av1_reconstruction:main --root tests \
    --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std" -o "$out/sanitized" tests/av1_reconstruction.zi
ASAN_OPTIONS=detect_leaks=1 UBSAN_OPTIONS=halt_on_error=1 "$out/sanitized/av1_reconstruction"
printf '%s\n' 'AV1 scalar zero-DC: 8/10/12-bit, stride/padding/bounds/cancellation source/saved C/Go/directVM + ASan/UBSan passed'
