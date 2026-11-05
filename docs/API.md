# AVIF package API

`avif/api` exports `Decode(input: BorrowedBytes, options: DecodeOptions) ->
DecodeResult`, `DefaultEngine() -> Av1Engine` and `LibaomOracle() -> Av1Engine`.
It reexports shared image-codec types. All output is owned `std/image.Image`.
Input is a synchronous borrow: keep its bytes alive and unchanged through the
call. No native decoder, allocation or native structure leaves the bridge.
Check `is_ok` before inspecting output. Move the owned result once.

`avif/engine` exports `Av1Engine`, `EngineCapabilities`, `ContainerDecode` and
`DecodeWithEngine(engine,input,options*)`. A caller can supply a fake engine
without linking any native codec. The initial callable boundary decodes a
complete container; `obu_planes=false` explicitly means it does not yet accept
extracted OBUs or return independently owned color/alpha planes. This avoids
misrepresenting libavif as an authored AV1 engine. An OBU/plane capability is a
future separately tested API extension.

Both native choices use the same libavif conversion and Ziran transform path.
`DefaultEngine` (and `Decode`) explicitly selects dav1d with its
runtime-dispatched assembly; `LibaomOracle` explicitly selects single-threaded
libaom, the comparison oracle. Selecting an unavailable native codec returns
`UnsupportedCapability`; there is no automatic fallback between them. Engines
have `container_bridge=true`, `strict_rgba8=true`, `fast_color=false`,
`hdr=false`, `interruptible=false` and `hard_scratch_limit=false`.
`max_threads` is the engine's bounded native fan-out inside its one worker
lease: 1 for libaom, and `AutoThreads()` (the device's usable cores capped at
`AUTO_THREADS`, 4) for dav1d. `DecodeWithEngine` rejects a bound below 1 or
above `MAX_DECODE_THREADS` (8).

## Decode semantics

The result is the first complete frame, with 8-bit straight (unpremultiplied)
RGBA, tightly packed top-to-bottom. 8/10/12-bit input and monochrome are
accepted. Clean aperture is applied first, then anticlockwise rotation, then
mirror, matching the prior Kryon implementation. Pixel aspect ratio is not
resampled. Metadata width/height describe transformed output; source bit depth,
alpha, source premultiplication, source total frame count and CICP remain source
properties. The shared `CopyImageToOutput` can copy to padded caller storage.

A multi-frame source is accepted with default `max_decoded_frames=1`.
`max_frames` independently caps the source frame count. No animation playback,
HDR output or gain-map rendering is implemented. FastColor, PQ, HLG, gain maps,
ICC color-management requests, and unavailable engine choices return
`UnsupportedCapability`. RGBA8 conversion of ordinary high-bit-depth SDR
sources does not imply HDR support. Strict output is byte-identical to the
saved libavif/libaom baseline on the package's 17 generated cases for both
engines and every thread count.

## Limits and errors

`avif/bmff.HasSignature(input: BorrowedBytes) -> bool` recognizes a prefix
containing the complete first 16–4096-byte `ftyp`, with major or compatible
`avif`/`avis` brand. It preserves the frozen host signature policy, including
accepting a major brand before inspecting compatible-brand alignment. Following
boxes may be absent or truncated. This predicate identifies a candidate AVIF;
it does not validate a full container, item graph or bitstream. `ValidateContainer`
and `Preflight` perform their separate bounded framing/metadata validation.

The shared positive limits are checked before work. Hard package maxima are
256 MiB input, 32768 per source axis, 67108864 source pixels and 4096 source
frames, even if callers raise shared limits. Lower caller input, dimensions,
pixels, output bytes, source frames and metadata limits are honored. The BMFF
preflight conservatively counts non-mdat/non-idat leaf payloads as container
metadata, including unknown leaves; it can reject metadata-heavy files before
libavif allocation. It caps known-container nesting at 16 and box count at4096.
This is bounded framing/preflight, not yet complete AVIF item graph validation.

`max_working_bytes` bounds the package-owned full-source RGBA conversion buffer
used for owned or transformed output. Direct identity caller output needs no
RGBA scratch allocation or working-byte reservation. Worker accounting reserves
needed scratch separately from owned output. It does
**not** bound libavif/libaom/dav1d's opaque internal allocation or process RSS.
There is no hard total engine-memory guarantee in this bridge. Consumers that
require that guarantee must inspect `hard_scratch_limit=false` and decline it.

One worker lease includes the caller. dav1d decode and libavif's row-split
RGB conversion share one automatic count, `DecodeThreads(pixels, format)`:
4:2:0 frames below `THREADED_MIN_PIXELS_420` (8388608, 8 MiP) and other
frames below `THREADED_MIN_PIXELS` (2097152, 2 MiP) use one thread; larger
frames use `AutoThreads()`, the process's usable cores (affinity mask; Windows
active processors; macOS online cores) clamped to 1..`AUTO_THREADS` (4). The
thresholds are measured: on an 8x Cortex-A53 phone, threading slowed smaller
frames by up to 2.7x. Thread count never changes output bytes.
libaom is built without multithreading. Every successful lease/reservation is
released on all return paths.
Cancellation is checked before work, after parse, after full-frame decode,
after conversion and once per transformed output row. Native parse/decode and
conversion calls cannot be interrupted. The shared cancellation flag is
single-thread cooperative state; do not concurrently mutate it during FFI.

Errors use image-codec `DecodeError` codes and absolute input offsets when the
Ziran parser knows them, otherwise -1. Bad lengths/truncated boxes return
`TruncatedInput`; invalid box sizes/crops/codec data return `MalformedInput`;
unknown brands/capabilities return `UnsupportedCapability`; budget/dimension
failures return `LimitExceeded`; pre-cancellation returns `DecodeCancelled`.
The ftyp-only fixture named `malformed.avif` returns `TruncatedInput` because
libavif needs the missing metadata. Failed results contain no output pixels.
Native allocation failures map to `AllocationFailed`, unavailable codecs to
`UnsupportedCapability`, and native malformed bitstreams to `MalformedInput`.

## Current validation limits

The bridge is native C target only. BMFF framing/transforms and fake-engine
contracts can execute as source/saved IR through native C and portable ZX.
No full native bridge Go/ZX/WASM implementation, Android/ARMv7, AArch64, grid,
progressive-layer, ICC, HDR or full AV1 conformance claim follows from this
initial Linux x86-64 suite. There is no benchmark or 10x efficiency claim.

## Optional native function-table interop

`avif/bridge` has no static AVIF/AOM foreign declarations or dependency links.
It owns the explicit libavif1.3 ABI types and `AvifAPI` callback table. Hosts
may fill that table with `dlsym` results and keep the library loaded throughout
each synchronous call. `api.version` must report exactly `1.3.0`; other versions
return `UnsupportedCapability` before create/defaults/record access. All table
slots must be present. Pinned-header sizeof/offsetof tests cover touched fields.
This ABI is not claimed compatible with libavif1.4 or arbitrary system builds.

`DecodeWithAPI(api,input,options,codec=CodecDav1d,threads=0)` returns the
normal owned result. `BridgeProbe(api,input,options,codec=CodecDav1d)` returns
`ProbeResult {is_ok,metadata,error}` from a bounded container parse, without
decoding or allocating pixel planes.
`DecodeIntoWithAPI(api,input,output,options,codec=CodecDav1d,threads=0)` returns
`DecodeIntoResult {is_ok,metadata,error,output_may_be_modified}`.
`CodecLibaom` (1) and `CodecDav1d` (2) are the only choices; others, and a
library built without the chosen codec, explicitly fail with
`UnsupportedCapability`. `threads=0` applies `DecodeThreads`; 1..8 is an
explicit count for both stages and anything else is rejected before decoding. Static hosts obtain
an equivalent table with `StaticNativeAPI()` from `avif/api`; they explicitly
link artifact outputs. The package has no unconditional native link libraries.

Probe is a sizing hint, not a retained decoder: Into re-parses the input and
revalidates the actual transformed dimensions, stride and capacity. Keep input
alive and unchanged for each call. Bad layout/capacity or pre-cancellation
writes nothing. Untransformed output converts directly into caller storage,
including padded rows. Transformed output uses one full-source RGBA scratch
buffer, then writes transformed pixels into the caller's stride. No owned
output frame or extra full-frame copy is allocated in Into.

After native conversion starts, a failure can leave arbitrary image bytes
written; after transform copying starts, complete visited source rows may have
been scattered to output. `output_may_be_modified=true` explicitly reports this
possibility, including success. Padding is untouched. Failed direct conversion
has no rollback guarantee. The buffer never becomes owned by DecodeResult.

## Authored container slice (internal)

`boxes.zi`, `items.zi`, `properties.zi` and `parse.zi` implement bounded still
item/property/reference graphs independently of the native engine. Internal
`ParseAvif(input,limits)` returns a fixed-capacity `AvifContainer` and error;
`ExtractItem(input,container*,id,limits)` returns independent owned OBU bytes.
Limits are128 items,256 properties,1024 associations,512 reference edges and16
extents per item, in addition to framing/input limits. Duplicate required boxes,
item declarations, locations, associations, transform properties and reference
edges reject deterministically; missing/dangling indices and out-of-file spans
reject before copying. File-offset and idat-relative extents are supported;
external data references, item-offset construction and grids/dimg reject.

The parser extracts primary/alpha payloads, av1C depth, clap/irot/imir and prem
relationships for the generated fixtures. It preserves bounded color property
bytes but does not implement color management, AV1 pixel reconstruction, grid
composition or track-based animation semantics. It remains internal until these
capabilities and conformance are complete. The native facade remains default.

## Internal scalar planar output

`color.zi` consumes borrowed `PlanarImage` views, containing `PlaneView` Y/U/V
and optional full-resolution alpha plus `ColorSpec`. Samples are unsigned
little-endian, one byte for8-bit and two for10/12-bit. The descriptor carries
depth, full/limited range, matrix, subsampling shifts, monochrome, explicit
nearest/bilinear filter and transfer characteristics. Monochrome ignores empty
U/V views and accepts unspecified matrix2 without guessing a color matrix.
Color accepts identity GBR (444), BT.709, BT.601 matrices5/6 and BT.2020NCL;
420/422/444/400 and odd dimensions are supported. Unknown color matrices and
PQ/HLG reject. Chroma positioning is centered for bilinear filtering; other
chroma siting must be rejected by the integrating container/engine layer.

`ConvertRGBA8Into(source,output,options)->PixelWriteResult` produces straight
RGBA8 with caller stride. Scalar alpha rounding follows the pinned libavif
RGBA8 conversion boundary: nearest/444 coefficient paths unpremultiply after
quantization, while identity fallback and subsampled bilinear paths use full
precision first. No ICC, transfer conversion, HDR tone mapping, color-primary
conversion or display color management is performed.

`output.zi` validates borrowed `RgbaView` input and supplies
`TransformRGBA8Into` for crop, anticlockwise rotation then mirror.
`grid.zi.ComposeGridRGBA8Into` accepts up to128 equal-size RGBA cells in
row-major order and clips the right/bottom cells to a validated `GridLayout`.
It does not parse AVIF grid items or decode cells.

These kernels allocate no pixel scratch. Plane spans are validated against
shared working limits; callers own and account for existing plane storage.
Caller output uses shared output-byte limits. Inputs and output must not
overlap; conservative whole-slice overlap validation uses portable pointer
equality and is linear in supplied slice lengths. All buffers, dimensions,
sample values and capabilities validate before writes. A worker lease covers
validation/conversion and releases on every return; callers already holding
the lease must pass options without acquiring the same budget again.
Cancellation is cooperative at row boundaries. `PixelWriteResult` reports
`is_ok`, `error` and `output_may_be_modified`, including possible completed
writes on cancellation. These modules remain internal and do not change the
default native facade.
