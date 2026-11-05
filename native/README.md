# Optional native oracles

Package source pins (resolved through `ziran add --source --ref COMMIT`):

- libavif 1.3.0: https://github.com/AOMediaCodec/libavif.git,
  `1aadfad932c98c069a1204261b1856f81f3bc199` (BSD-2-Clause).
- libaom 3.13.1: https://aomedia.googlesource.com/aom,
  `d772e334cc724105040382a977ebb10dfd393293` (BSD-2-Clause and patent grant).
- dav1d 1.5.4: https://github.com/videolan/dav1d.git,
  `54706fc6bc0cdecab7e9593974a4039cc038fca7` (BSD-2-Clause).

`native` supplies a self-contained optional `libavif_bridge.so`, static libavif/libaom, licenses, patent text, link metadata
and exact source provenance. `native-dav1d` additionally supplies static dav1d
and its license, enabling explicit choices in the same libavif build. Source
HEADs must equal the declared pins and source trees must be clean. Sources
are read through package resolution; no downstream vendor files are edited.
Outputs and SHA-256 descriptors are published by Ziran's native recipe cache.

Only `linux-x86_64-gnu` is currently accepted. Other platforms fail explicitly.
Both recipes build decode-only, single-threaded libaom, no libyuv/libsharpyuv,
no encoders/apps/examples/tests. dav1d retains NASM SIMD and its normal CPU
dispatch; the .zi bridge requests one thread for either engine.

Static CMake consumers include this package's `native/ZiranAvif.cmake` and call:

```cmake
include("${AVIF_PACKAGE}/native/ZiranAvif.cmake")
ziran_avif_add_native(AVIF_SOURCE "${LOCKED_LIBAVIF}" AOM_SOURCE "${LOCKED_AOM}")
target_link_libraries(my_decoder PRIVATE ziran_avif::static)
```

The function validates the same exact source pins and clean trees. It supplies
the complete static link requirements through `ziran_avif::static`; the raw
`avif_static` and `aom` targets and `avif/libavif.a`, `aom/libaom.a` layout remain
available. `BUILD_SHARED_BRIDGE` additionally creates the real `avif_bridge`
target on Linux. `SHARED_TARGET_NAME kryonavif` preserves a consumer's existing
build target and binary name; `SHARED_OUTPUT_NAME` optionally changes only the
binary name. `WITH_DAV1D DAV1D_SOURCE path` validates the dav1d pin too and
requires the pinned recipe's1.5.4 pkg-config installation.
There is no second codec recipe in the consuming project.

Linux and Android consumers share decoder-only, PIC, encoder/apps/tests/tools
off and `CONFIG_MULTITHREAD=0` policy. Android arm64 selects `AOM_TARGET_CPU=arm64`;
ARMv7 selects `armv7` and `ENABLE_NEON=OFF`, retaining the frozen alignment-safe
portable CfL path. Existing Windows/Darwin static configure paths are preserved;
their presence is not evidence of execution on those systems. The artifact CLI
remains Linux x86-64 only. Android execution and ARMv7 alignment safety still
require downstream device validation.

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
ziran pkg artifact avif:native-dav1d --platform linux-x86_64-gnu
```

Run build-producing commands through `build-queue --`. A recipe is requested
from a consumer with a locked `avif` dependency; `self:native` is not a public
root artifact command. The tests create this consumer inside ignored build
intermediates without requiring an empty bootstrap commit.

The dav1d recipe needs the exact Python build tools in `requirements.txt`,
CMake, Make, pkg-config, a native compiler and NASM. Install missing build-only
tools explicitly into this checkout (the recipe does not fetch tools):

```sh
build-queue -- python3 -m pip install --target build/native-tools -r native/requirements.txt
```

No global Python environment or system packages are changed. Native artifacts
contain upstream C/assembly engine code; handwritten package product source is
Ziran. Recipe/build/test orchestration uses Python, shell, CMake and Make.
