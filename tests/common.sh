#!/bin/sh
set -eu
unset DISPLAY WAYLAND_DISPLAY WAYLAND_SOCKET XAUTHORITY DBUS_SESSION_BUS_ADDRESS DBUS_SYSTEM_BUS_ADDRESS SESSION_MANAGER XDG_RUNTIME_DIR
export ZIRAN_DESKTOP_RECOVERY=0 HARMONY_DESKTOP_RECOVERY=0 YUE_DESKTOP_RECOVERY=0
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
toolchain=${ZIRAN_ROOT:-$root/../../ziran}
if test ! -x "$toolchain/build/bin/ziran"; then toolchain=$(ziran pkg path ziran); fi
ziran=${ZIRAN_BIN:-$toolchain/build/bin/ziran}
foundation=${IMAGE_CODEC_ROOT:-$("$ziran" pkg path image_codec)}
export ZIRAN="$ziran"
mkdir -p "$root/build/scratch/tmp" "$root/build/bin"
export TMPDIR="$root/build/scratch/tmp"
ulimit -c 0
cd "$root"
