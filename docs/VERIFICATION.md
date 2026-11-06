# AVIF implementation receipt

The stable public facade uses the pinned libavif bridge. The authored AV1
decoder lives in the separate av1 package, remains in development and is
outside this publication. The
receipts below describe local tests with recorded source identities; they do
not establish GitHub checks, a release or installation.

The imported callback compiler blocker is resolved in the canonical toolchain.
`build-queue -- sh tests/avif.sh` completed successfully, including the actual
no-static-link dlopen loader, source/saved IR and all17 frozen native goldens.
The final combined run of `sh tests/bridges.sh` plus the benchmark also
completed successfully under build-queue with pinned
libavif1.3.0, AOM3.13.1 and dav1d1.5.4. Old fixtures/goldens were preserved.
On 2026-11-06 the libaom pin moved to 3.15.3; `build-queue -- sh tests/avif.sh`
passed again with both engines and the same frozen goldens. The benchmark below
was measured at AOM3.13.1 and has not been rerun.
The final suite includes the bounded scratch probe and scalar multi-target tests.
Exact final command and source identities: `receipts/integration-continuation.json`.

Implemented integration:

- `avif/bmff.HasSignature(BorrowedBytes)->bool` preserves frozen prefix-only
  AvifSignature behavior, separately tested from full framing/preflight.
- Identity/full-crop/zero-rotation Into passes the validated caller pointer and
  padded stride directly to native conversion, with no RGBA scratch allocation
  or working-byte reservation. Transform output retains one bounded source frame.
- `VecResizeBounded(...,count,count)` now caps bridge scratch and owned OBU
  backing capacity. An independent malloc/calloc/realloc linker probe observes
  zero identity pixel allocations and exactly24 bytes for a transformed3x2
  source with max_working_bytes24. This bounds requested element storage,
  not allocator overhead or opaque native engine allocations/RSS.
- Failed OBU extraction now returns its error instead of recursively invoking
  ItemFailure. Tests cover exact capacity, exact working ceiling, ceiling-1 and
  missing-item rejection, alongside all17 pinned OBU pairs and malformed graphs.
- `native/ZiranAvif.cmake` provides one pinned decoder-only recipe and complete
  `ziran_avif::static` link target. Linux/Android policy and ARMv7 NEON-off
  alignment-safe kernels match the frozen recipe. Custom real shared target
  names preserve existing consumers. Native artifact recipes serialize shared
  configure/build/dav1d install/staging; project-tool replacement is atomic.

Completed focused local tests (all build invocations through build-queue):

- `sh tests/bmff.sh`: source/saved C and direct portable VM, signature boundaries,
  framing/overflow/depth and independent rectangular orientations.
- `sh tests/into_contract.sh`: source/saved C with no codec linkage, direct
  destination/zero scratch, independent allocation probe, transformed reservation,
  padding/sentinels, capacity/stride, failures/cancel and modification reporting.
- `sh tests/static_into.sh` and `sh tests/dynamic.sh`: source/saved real native
  owned/probe/padded Into outputs on17 fixtures, error and ABI contracts.
- `sh tests/abi.sh`: pinned-header sizeof/offsetof for every declared bridge
  record field, source/saved C. RawDecoder is intentionally a public ABI prefix;
  its total sizeof is not claimed equal to the native full decoder.
- `sh tests/native_recipe.sh`: actual independent include/static link/execute
  matches the frozen RGBA golden, verifies pinned flags and wrong-pin rejection,
  separate-process lock exclusion and preservation under injected staging failure.
- `sh tests/container.sh`: source/saved C,17 OBU goldens,9 malformed graph classes,
  every proper reference-file prefix and single-byte mutation; exact bounded OBU
  allocation and safe extraction failure paths.
- `sh tests/transforms_color.sh`:486 pinned synthetic plane cases, independent
  clipped grids and crop/orientation expectations, padded rows/sentinels,
  unsupported/invalid/overlap/limits/cancellation rejection, source/saved C,
  Go with cgo disabled and directVM. Pure C executables have no codec references.
- Fixture verification retains103 baseline binary/text digests.

The downstream Kryon worker reports integrated source/saved native/dynamic
and sanitizer tests plus four Android Release ABI links passing after bounded
scratch. This is downstream evidence, not an Android execution claim. Device
execution and Windows runtime remain unverified by this worker.

Authored scalar output work is isolated from the default compatibility bridge:
`color.zi`, `alpha.zi`, `output.zi`, `grid.zi` implement planar conversion,
straight-alpha processing, crop/rotation/mirror and clipped row-major RGBA grid
composition. Synthetic oracle generation has486 cases across8/10/12-bit,
full/limited range, identity/BT.601/BT.709/BT.2020NCL,400/444/422/420,
nearest/bilinear chroma and alpha/premultiplication. Actual source and saved IR pass all 486 cases in native C, Go with cgo disabled
and direct portable VM, alongside padded geometry/grid/rejection contracts.
Numeric pointer casts proved unavailable on Go/directVM; overlap validation
uses portable pointer equality instead. The generic compiler reproducer was
recorded upstream, but is no longer a product validation blocker.
No AVIF grid-container parsing, full color-management or default-engine switch
is claimed by these standalone kernels.

Post-integration benchmarks:

`build-queue -- env AVIF_LOCAL_INPUT=/mnt/storage/Projects/kryonlabs/kryon/tests/fixtures/avif/jungle-title.avif sh tests/benchmark.sh`
passed after bounded bridge scratch landed. Each engine receives16 warm
full-file read/decode/allocate samples, one worker, with exact output validation.
Both use libavif1.3.0 conversion. Pinned engines are AOM3.13.1 and dav1d1.5.4.
Tiny p50: 156961 ns and 59791 ns. Local1024x1536 p50:
36733078 ns and 23235512 ns (about 1.58x in this run). libavif1.4.2/AOM3.15.1 remains unvalidated. No current
fastest,10x, hardware, cold-cache, cross-machine or energy claim follows.

Scalar oracle provenance: `receipts/scalar-output-oracle.json`.

Persistent benchmark receipts: `receipts/tiny-comparison.json` and
`receipts/local-comparison.json`, with source/compiler/runner identities, input
and output hashes, CPU/allowed CPUs, samples, process CPU and peak RSS.
Allocator counts and energy are unmeasured in those benchmarks. The Jungle
input is local-only and is not redistributed.
