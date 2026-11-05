#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
sh tests/avif.sh
consumer="$root/build/scratch/avif/consumer"
native=$(cat "$root/build/scratch/avif/native-artifact.txt")
base=$(dirname "$native")
# libavif.a is libavif merged with the dav1d codec.
export AVIF_LIB_DIR="$base/lib" AVIF_EXTRA_LIBS="-lpthread -ldl"
AVIF_ENGINE=libaom sh tests/bridge_core.sh
AVIF_ENGINE=dav1d sh tests/bridge_core.sh
printf '%s\n' 'AVIF libaom + dav1d: complete-file strict RGBA and error classes passed'
