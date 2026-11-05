#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
out="$root/build/scratch/transforms-color"
mkdir -p "$out"
consumer="$root/build/scratch/avif/consumer"
artifact=$(cat "$root/build/scratch/avif/native-artifact.txt")
base=$(dirname "$artifact")
if ! test -f "$base/lib/libavif.a" || ! test -f "$base/lib/libaom.a"; then
    artifact=$(cd "$consumer"; "$ziran" pkg artifact avif:native --platform linux-x86_64-gnu)
    base=$(dirname "$artifact")
fi
headers=$("$ziran" pkg path libavif)
"${CC:-cc}" -std=c11 -O2 -I"$headers/include" tests/color_oracle.c "$base/lib/libavif.a" "$base/lib/libaom.a" -lpthread -ldl -lm -o "$out/color_oracle"
"$out/color_oracle" >"$out/oracle.txt"
python3 tests/color_oracle.py "$out/oracle.txt" "$out/color_cases.zi"
"$ziran" ir --root tests --module-path "$out" --module-path "$root/src" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std" -o "$out/ir" tests/transforms_color.zi
status=0
for form in source saved; do
    input="$root/tests/transforms_color.zi"
    set -- --root tests --module-path "$out" --module-path "$root/src" --module-path "image_codec=$foundation/src" --module-path "std=$toolchain/std"
    if test "$form" = saved; then input="$out/ir/transforms_color.zir"; set -- --root "$out/ir" --module-path "$out/ir"; fi
    LDLIBS= "$ziran" build --target=c --exe --entry transforms_color:main "$@" -o "$out/$form-c" "$input"
    "$out/$form-c/transforms_color"
    if nm -u "$out/$form-c/transforms_color" | rg -q 'avif|aom|dav1d'; then exit 1; fi
    "$ziran" bundle --entry transforms_color:main "$@" -o "$out/$form.zx" "$input"
    "$toolchain/build/bin/zi2zx-vm" run "$out/$form.zx" >"$out/$form-vm.txt"
    tail -n 1 "$out/$form-vm.txt" | rg -q '^0$'
    LDLIBS= "$ziran" build --target=go --pkg main --exe --entry transforms_color:main "$@" -o "$out/$form-go" "$input"
    if (cd "$out/$form-go"; CGO_ENABLED=0 GO111MODULE=off GOWORK=off GOMAXPROCS=1 go build -p=1 -o transforms_color .); then
        "$out/$form-go/transforms_color"
    else
        status=1
    fi
done
exit "$status"
