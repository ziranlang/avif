# Optional native oracles

Package source pins (resolved through `ziran add --source --ref COMMIT`):

- libavif 1.3.0: https://github.com/AOMediaCodec/libavif.git,
  `1aadfad932c98c069a1204261b1856f81f3bc199` (BSD-2-Clause).
- libaom 3.13.1: https://aomedia.googlesource.com/aom,
  `d772e334cc724105040382a977ebb10dfd393293` (BSD-2-Clause and patent grant).
- dav1d 1.5.4: https://github.com/videolan/dav1d.git,
  `54706fc6bc0cdecab7e9593974a4039cc038fca7` (BSD-2-Clause).

`native` supplies a self-contained optional `libavif_bridge.so`, static
`libavif.a` (libavif merged with the dav1d codec), static libaom, licenses,
patent text, link metadata and exact source provenance. dav1d is the default
engine; libaom is the explicit comparison oracle in the same libavif build.
There is no separate dav1d artifact and no fallback between the codecs.
Source HEADs must equal the declared pins and source trees must be clean.
Sources are read through package resolution; no downstream vendor files are
edited. Outputs and SHA-256 descriptors are published by Ziran's native recipe
cache.

The artifact CLI accepts only `linux-x86_64-gnu`; other platforms fail
explicitly and are built through the CMake function below. Every build is
decode-only, with no libyuv/libsharpyuv and no encoders/apps/examples/tests.
libaom is single-threaded (`CONFIG_MULTITHREAD=0`). dav1d is built by Meson
with `enable_asm=true`, release DSP trimming and its normal runtime CPU
dispatch. The bridge requests a bounded thread count (see docs/API.md).

Static CMake consumers include this package's `native/ZiranAvif.cmake` and call:

```cmake
include("${AVIF_PACKAGE}/native/ZiranAvif.cmake")
ziran_avif_add_native(AVIF_SOURCE "${LOCKED_LIBAVIF}" AOM_SOURCE "${LOCKED_AOM}"
                      DAV1D_SOURCE "${LOCKED_DAV1D}")
target_link_libraries(my_decoder PRIVATE ziran_avif::static)
```

The function validates the same exact source pins and clean trees. It supplies
the complete static link requirements (threads, dl, m) through
`ziran_avif::static`; the raw `avif_static` and `aom` targets and
`avif/libavif.a`, `aom/libaom.a` layout remain available. dav1d is configured
from a Meson machine file derived from the CMake compiler, target, sysroot and
flags (a cross file when cross-compiling, mapped to its CPU family), built
into `dav1d-install` and merged into `libavif.a`, so consumers link the same
two archives as before. `ZIRAN_AVIF_DAV1D_JOBS` bounds its Ninja jobs (4).
`BUILD_SHARED_BRIDGE` additionally creates the real `avif_bridge` target on
Linux. `SHARED_TARGET_NAME kryonavif` preserves a consumer's existing build
target and binary name; `SHARED_OUTPUT_NAME` optionally changes only the
binary name. There is no second codec recipe in the consuming project.

Android arm64 selects `AOM_TARGET_CPU=arm64`; ARMv7 selects `armv7` and
`ENABLE_NEON=OFF` for the libaom oracle only, retaining its frozen
alignment-safe portable CfL path. dav1d keeps its NEON assembly on ARMv7.

libavif compiles without floating-point contraction (`-ffp-contract=off`):
compilers that fuse multiply-adds by default (GCC on AArch64, Clang on arm64)
otherwise converted the same frame to different RGBA bytes.

| target | default engine | asm in libavif.a | proof |
|---|---|---|---|
| Linux x86-64 | dav1d, auto threads | SSE2..AVX-512 (Ice Lake) | executed; strict parity, benchmark per tier |
| Android armeabi-v7a | dav1d, auto threads | NEON | executed on USB Moto (MT6765); strict parity, benchmark |
| Android arm64-v8a | dav1d, auto threads | NEON, dotprod, i8mm | static build executed under qemu-user (Cortex-A53, max); strict parity |
| Android x86 / x86_64 | dav1d, auto threads | SSSE3, SSE4.1 / + AVX2, AVX-512 | static build executed on the x86-64 host; strict parity |
| Linux AArch64 | dav1d, auto threads | NEON, dotprod, i8mm | executed under qemu-user (Cortex-A53, max); strict parity |
| Windows, macOS | configure paths exist | unverified | not executed here |

Kryon runs these proofs (`make android-avif-test`, `make avif-cross-test`,
`make avif-benchmark`) through its own consumer of this recipe.

Both artifact recipes hold one package-owned `build/native-recipe.lock` across
source validation, configure, build, dav1d installation and output staging, so
different consumers cannot mutate the shared trees concurrently. All files are
staged before any output is replaced, then each completed file is renamed into
the package manager's unpublished transaction. Ziran publishes the complete
transaction only after validating declared output hashes. A failed build or
stage preserves previously published artifacts. Project-tool updates use an
atomic executable replacement, preserving readers of the previous version.

A consumer requests:

```sh
ziran pkg artifact avif:native --platform linux-x86_64-gnu
```

Run build-producing commands through `build-queue --`. A recipe is requested
from a consumer with a locked `avif` dependency; `self:native` is not a public
root artifact command. The tests create this consumer inside ignored build
intermediates without requiring an empty bootstrap commit.

Every native build needs Meson and Ninja for dav1d, plus NASM on x86. The
artifact recipe uses the exact Python build tools in `requirements.txt`;
CMake consumers use `ZIRAN_AVIF_TOOLS` (variable or environment) naming such a
directory, else this checkout's `build/native-tools`, else Meson and Ninja on
`PATH`. Install missing build-only tools explicitly (nothing is fetched):

```sh
build-queue -- python3 -m pip install --target build/native-tools -r native/requirements.txt
```

No global Python environment or system packages are changed. Native artifacts
contain upstream C/assembly engine code; handwritten package product source is
Ziran. Recipe/build/test orchestration uses Python, shell, CMake and Make.
