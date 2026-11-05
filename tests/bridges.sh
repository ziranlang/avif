#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
sh tests/avif.sh
consumer="$root/build/scratch/avif/consumer"
native=$(cd "$consumer"; "$ziran" pkg artifact avif:native-dav1d --platform linux-x86_64-gnu)
base=$(dirname "$native")
printf '%s\n' "$native" >"$root/build/scratch/avif/dav1d-artifact.txt"
export AVIF_LIB_DIR="$base/lib" AVIF_EXTRA_LIBS="$base/lib/libdav1d.a -lpthread -ldl"
AVIF_ENGINE=aom sh tests/bridge_core.sh
AVIF_ENGINE=dav1d sh tests/bridge_core.sh
printf '%s\n' 'AVIF libaom + dav1d: complete-file strict RGBA and error classes passed'
