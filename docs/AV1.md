# Owned AV1 engine

The authored engine is under `src/av1`. Its validated V01 layer implements
bounded syntax bits, LEB128/OBU framing and the scalar arithmetic symbol
decoder. The V02 sequence parser and shown-key frame control parser also
pass the header differential suite. A first narrow authored path reconstructs
owned 8/10/12-bit monochrome and color YUV for lossless intra blocks with all ten partition
types, including nonzero 4x4 coefficients, in pictures with each dimension and
sequence maximum 1..64. Both reduced still headers and full shown-key headers
are implemented. Supported
prediction modes include all thirteen intra modes, all seven directional angle
deltas, intra edge filtering/upsampling, all five recursive filter-intra predictors
and luma/chroma palettes of two through eight colors. Color supports 4:2:0,
4:2:2 and 4:4:4 with chroma-from-luma prediction.
Lossy transforms, intraBC, reference frames and frame-level filtering remain
unfinished. Film-grain output is implemented for this bounded lossless path and
passes encoded-frame parity. This is not a complete AV1 decoder, conformance or
speed claim. The AVIF bridge remains a separate engine.

Product codec code is handwritten `.zi`. Generated C/Go and portable `.zx`
execute the same scalar semantics. No upstream decoder is called by the
authored modules. Native upstream libraries are test oracles only. Internal
modules use explicit package-local file imports, without new public exports.

## V01 contracts

- `NewBits(input,begin,end)` creates an MSB-first syntax `BitReader` over an
  absolute byte interval. `ReadBits(reader*,count)` reads 0–32 bits. Failed
  reads return zero, preserve the cursor, and retain the first `DecodeError`.
  `AlignBits` requires zero alignment bits; `FinishBits` requires a one followed
  by zero bits to the interval end. Neither operation decodes entropy symbols.
  `ReadSignedBits` handles 1–32-bit two's-complement literals; `ReadNS` handles
  bounded AV1 non-symmetric literals, including `n=1` without consuming input.
- `ReadLEB128(input,at,end)` returns `value`, `bytes`, `next`, and `error`.
  Non-minimal encodings are legal, including eight-byte encodings. Values
  greater than UINT32_MAX, or continuation on byte eight, are malformed.
- `ReadOBU(input,at,end,external_size=false)` returns an `ObuView` with absolute
  `start`, `payload`, `end`, type and layer IDs. Reserved types remain skippable.
  Missing size fields require an explicit enclosing one-OBU length. With
  `external_size=true`, an internal length must agree with that enclosing end.
  Header forbidden/reserved bits are validated; payload interpretation belongs
  to the next stage.
- `NewRange(input,begin,end,disable_cdf_update=false)` constructs the AV1 symbol
  decoder. `ReadSymbol(decoder*,cdf)` takes an **ascending** Q15 CDF: 2–16
  probabilities in `[0,32768]`, nondecreasing, terminal probability 32768,
  followed by the adaptation count in `[0,32]`. Equal probabilities are tested
  against libaom. This differs from the inverse CDF representation in native
  oracles. `ReadBool` and `ReadLiteral` decode entropy literals. They are not
  replacements for syntax `ReadBits`.
- Symbol decoding uses the specification's complemented range value and
  bounded virtual zero padding. Reads past the permitted padding return
  `TruncatedInput` at the interval end. `FinishRange` verifies `exit_symbol`'s
  one bit and zero tail and rejects reuse after success. Callers must finish a
  tile; decoding a symbol alone does not validate its termination.

Input slices borrow caller storage synchronously; keep it alive and unchanged.
There are no allocations, threads, globals or retained callbacks in V01.
Arithmetic and source bounds are checked before indexing, addition or narrowing
that depends on untrusted lengths. Errors use `image_codec.DecodeError`, with
absolute byte offsets; callers check `error.code` before using results.
Cancellation/working-memory/owned-plane scheduling belongs to the experimental
engine entry described below; primitive header parsers do not acquire leases.

## First owned reconstruction path

`DecodeAv1YUV(input,options*) -> Av1YUVResult` is internal and experimental.
It accepts one shown KEY picture with implemented luma/chroma intra modes,
lossless quantization, square/rectangular partitions and one tile. Frame width
and height and sequence maxima must each be 1..64. Full headers may override
frame dimensions within the sequence maximum. It owns OBU/header/tile framing, partition, skip/mode, 4x4
coefficient entropy, range termination, scalar intra prediction and inverse WHT
reconstruction and displayed film-grain output. Lossy transforms and intraBC
reject explicitly. Screen-content palette syntax includes adaptive presence/size,
neighbor color caches and the complete diagonal index map.
Lossless syntax disables
the reconstruction filters in this subset. This function calls no native codec.

`Av1YUVResult` contains `is_ok`, `error`, sequence/frame metadata and shared
owned `Plane` fields `y`, `u`, `v`. For monochrome only Y is populated. Color
returns all three planes with chroma dimensions rounded up from source subsampling. Samples
are one byte at depth8 and little-endian two-byte values at depth10/12, tightly
packed with `stride = width * sample_bytes`. Input can be released or changed after the call. Normal
owned Vec lifetime/move rules apply; no input/reference/callback is retained.
The planes hold source-depth displayed YUV samples, including signalled film grain,
without range expansion, RGB conversion,
alpha composition or premultiplication. Sequence fields `bit_depth`,
`monochrome`, `profile`, `color_description_present`, `color_primaries`,
`transfer_characteristics`, `matrix_coefficients`, `full_range`,
`subsampling_x/y` and `chroma_sample_position` preserve the AV1 metadata.
The container/color layer must reconcile its BMFF metadata separately.

The entry validates options/input, leases one caller worker and reserves a
conservative 1MiB bound for this fixed path's control/CDF scratch before parsing.
It launches no threads. The sum of returned plane byte counts is charged separately to
`max_output_bytes`. `VecResizeBounded` caps each backing capacity to its exact plane
byte count; tests inspect capacity as well as length. Worker and scratch leases release on every return. This
per-call accounting is not a process-RSS cap or an aggregate limit on outputs
that callers deliberately retain. Cancellation is cooperative at stage/row
checkpoints under the shared single-thread token contract.

For this fixed-size path, the memory receipt records actual generated native
sizes for the tile, reconstruction result, coefficient/partition/mode/filter
CDFs, sequence/frame headers and public result. It conservatively counts two tile
records, three separate reconstruction results, four sequence/frame records,
two public results, three copies of each CDF factory result and two copies of
coefficient/prediction/residual temporaries. Grain control records, noise arrays,
lookup tables and returned pictures have separate conservative copy counts.
Embedded arrays are intentionally counted again in those separate copies.
The bound adds 32KiB for scalar helpers and at most six recursive partition
frames, plus 66,144 bytes for grain stripe and Gaussian-table temporaries.
The current logical codec bound is 570,050 bytes.

The native local test recompiles the actual generated translation units with
`-O2 -fstack-usage`. Summing every nonrecursive function frame together and
adding six extra copies of the largest recursive frame gives a separate native
stack bound, currently 439,544 bytes. Both bounds must fit the 1MiB reservation for the local test to pass. Exact sizes,
copy counts, function evidence and commands are saved in the engine's memory
receipt. This derivation covers the current <=64 lossless algorithm including grain
and must be recomputed when dimensions, chroma or transform scratch expand.
Allocator size classes, Go/VM/runtime housekeeping, caller-retained outputs and
physical RSS are excluded; this is not a process memory limit.

Run `build-queue -- sh tests/av1_engine_parity.sh` and
`build-queue -- sh tests/av1_reconstruction.sh`. Real 8/10/12-bit AV1 still
fixtures are independently decoded and symbol-traced by pinned libaom. Native
source/saved IR, generated Go and direct VM must return the same owned planes.
Tests cover repeated ownership/drop, every truncated prefix, cancellation,
worker saturation, scratch/output caps and scalar stride/padding/overflow.
Native allocator fault injection and sanitizers verify allocation failure and
lease cleanup. FFmpeg/libaom is used only to generate test inputs; its command,
version and fixture digests are recorded under ignored build artifacts.

These tiny lossless samples are an initial semantic path, not the required
AVIF fixture compatibility or pinned full-frame conformance corpus. Do not
select this engine as the facade default. RGB conversion, alpha composition,
general frame tools and the rest of V03–V06 still need implementation.

`ReadLosslessCoefficients4x4(decoder*,cdfs*,skip_context,dc_context,token)`
decodes one luma transform in fixed storage. It implements EOB, coefficient
base/BR symbols, signs, bounded Golomb suffixes, coefficient masking and
above/left context summaries. `CoeffCDF4x4` belongs to a tile and adapts across
its transforms. `quant[16]` uses specification row-major positions; the libaom
oracle uses transposed coefficient storage. Check `error` before reading a
returned block. The supplied contexts must be in `[0,6]` and `[0,2]`.

`InverseLossless4x4(quant,depth,token)` is the scalar dequantization/inverse WHT
reference. It widens arithmetic, clamps intermediate values as specified and
rejects nonconforming residual ranges without exposing samples. Output
residuals are signed row-major values; clipping to the sample depth happens
after adding the prediction. The supported tile performs these operations
in raster order and updates both level and DC-sign neighbor contexts.

`partition.zi` owns the partition probability contexts. The tile traverses
NONE/HORZ/VERT/SPLIT, A/B and 1:4 nodes in the specified order, with a hard
1,024-node bound and at most six recursive frames. Block-size
and skip grids, coefficient levels and DC signs are tile-owned fixed storage.
They update across coding blocks, not separately for each 8x8 block. Boundary
nodes outside both half-block boundaries force a split. A node crossing just
one boundary uses the specification's transient split-or-horizontal/vertical
CDF; this does not adapt the underlying partition distribution. Reconstruction
uses the padded MiCols/MiRows footprint and crops samples into the actual output
dimensions without retaining padded bytes in the returned plane.

`build-queue -- sh tests/av1_still_partitions.sh` compares 108 larger native
lossless inputs, including encoder-forced 8x8 split trees and intra controls.
All 108 planes match libaom across 1,189 coding blocks. Separate native-decoded standard whole-frame
vectors exercise all ten partition types, including rectangular blocks.
Both skipped blocks and explicit empty coefficient transforms are covered.
The native oracle reports actual block sizes and modes instead of assuming the
encoder honored its controls. Sizes16/32/64 and all three bit depths run from
source/saved IR in C, Go, direct VM and under ASan/UBSan.

`build-queue -- sh tests/av1_boundaries.sh` adds78 real tiny, odd and rectangular
frames at8/10/12 bits. It includes1x1,3x5,9x9,10x23,24x40,33x17 and63x64
boundaries. Native planes, exact backing capacity, source/saved IR, C/Go/direct
VM, output limits and sanitizers are verified.

`build-queue -- sh tests/av1_coefficients.sh` tests 36 real encoder-produced
lossless inputs. Implemented intra modes match pinned libaom pixels, including
nonzero DC, signed checkerboards, an impulse and exact vertical/horizontal
prediction. Every supported input prefix rejects without planes or
retained leases. Another 512 deterministic arbitrary-entropy cases exercise
bounded rejection and repeatable errors; they are not conformance vectors.
The same suite checks default CDF provenance, 19 coefficient/Golomb boundary
streams from the pinned arithmetic encoder and two complete native-decoded
frames at the coefficient-mask boundary. `build-queue -- sh
tests/av1_scalar_kernels.sh` compares 387 signed impulse/random WHT vectors
against the integer specification and the pinned scalar libaom kernel.
Both suites run source/saved IR through C, Go, direct VM and ASan/UBSan.

`PredictIntra4x4` is the scalar reference for DC, exact vertical/horizontal,
Smooth/SmoothV/SmoothH and Paeth. The tile builds the specification's four-sample
edges and corner, selects the adaptive keyframe CDF from above/left block modes,
and handles directional modes through `PredictDirectional4x4`. The local suite
`build-queue -- sh tests/av1_prediction.sh` compares 672 native scalar vectors
across all edge availability combinations and sample depths, with boundary,
descriptor and cancellation cases on source/saved C/Go/direct VM and sanitizers.

`PredictFilterIntra4x4` implements the recursive seven-tap prediction for all
five filter modes. Each 4x2 group uses its preceding predicted row before
residual addition. The tile reads adaptive filter-presence probabilities by
coding-block size and a shared five-symbol filter-mode CDF when enabled.
`build-queue -- sh tests/av1_filter_intra.sh` compares 480 edge/random scalar
vectors and 180 native-decoded standard whole frames covering all five filters,
inactive filter flags, all ten partition types and all three sample depths.
Another 18 encoder-produced nonzero residual inputs exercise sequence-enabled
filter syntax, including 13 active filter blocks recorded by the native oracle.
Prefix truncation, invalid edges/modes,
cancellation, source/saved C/Go/direct VM and ASan/UBSan are included. Default
CDFs and tap constants are checked against the pinned upstream definitions.

`PredictDirectional4x4` accepts eight extended samples on each edge, a corner,
edge availability, directional mode, angle delta, sequence edge-filter flag,
neighbor-derived filter type and bit depth. It implements all three directional
zones, normative interpolation, edge filtering and half-sample upsampling for
the fixed 4x4 transform footprint. Signed floor division is explicit. Decoded
4x4 flags select above-right and below-left availability in actual partition
decode order. No sample is returned after failure/cancellation.
`build-queue -- sh tests/av1_directional.sh` compares 1,344 pinned scalar vectors
and 336 native-decoded standard whole frames across eight directional modes,
seven angle deltas, all ten partition types, both edge-filter states, both
neighbor filter types and all three sample depths. It runs source/saved IR
through C, Go, direct VM and ASan/UBSan; derivative constants are provenance-checked.

`tile_state.zi` owns fixed luma/chroma storage and neighbor state. `chroma.zi`
reconstructs U followed by V, sharing the normative UV probability models while
retaining separate level/DC contexts and sample buffers. Subsampled 4x4 luma
blocks consume chroma only at the specified reference block. Directional chroma
edges use plane-specific decoded flags. `chroma_modes.zi` reads UV modes,
shared angle probabilities and signed CfL alpha values. For lossless coding,
CfL is allowed exactly when the chroma coding footprint is 4x4.

`PredictCfl4x4` performs bounded source-luma subsampling, edge repetition, Q3
mean subtraction, signed alpha scaling and sample clipping. `build-queue -- sh
tests/av1_cfl.sh` compares 1,782 vectors against pinned native mean/prediction
kernels, covering every alpha from -16 through16, three subsampling modes,
three depths and clamped edges. Normal C is optimized; the large generated
vector host uses O0 for ASan/UBSan. Source/saved IR, Go and direct VM also run.

`build-queue -- sh tests/av1_chroma.sh` compares all three source-domain planes
for 189 actual lossless encoder inputs at8/10/12 bits and 4:2:0/4:2:2/4:4:4.
It includes tiny/odd dimensions through64, independent chroma patterns,
correlated luma/chroma, native CfL block observations and pinned UV model
provenance. Plane metadata/capacity, aggregate output limits, truncation,
retained results across repeated decodes, input independence and failure of
each of the three allocations are covered. Optimized C, Go, direct VM, saved
IR and ASan/UBSan run separately.

`palette.zi` owns luma/chroma palette parsing and fixed index-map storage.
`BuildPaletteCache` sorts and deduplicates the bounded above/left palette union.
`PaletteColorContext` derives the stable color order and context from the left,
diagonal and above indices. `ReadPaletteColors` reads sizes two through eight,
cache selection and source-depth colors. Luma deltas are positive; U permits
duplicate colors, while V uses literals or signed modular deltas. Metadata
for both palettes precedes `ReadPaletteMap`, which reads the non-symmetric first
index and adaptive diagonal tokens. `ReadPaletteBlock` combines the two steps
for monochrome callers. The map extends cropped indices to the coding-block edge
and commits its active count only on success. Tile-owned neighbor palette
records update across coding blocks. Reconstruction adds lossless residuals to
palette predictions; active palettes omit filter-intra syntax as specified.
The UV map selects paired U/V colors. UV cache records follow the luma MI grid,
including leaves without chroma, separately from chroma prediction availability.
`palette_uv_cdfs.zi` owns the independent adapted UV size/index probabilities.

`build-queue -- sh tests/av1_palette.sh` compares all 1,365 possible neighbor
contexts for sizes two through eight against the pinned native context routine.
It also verifies 210 native-decoded standard whole frames across all ten
partition types, cache reuse/union, palette sizes and all sample depths. Another
81 encoder-produced inputs include tiny/odd sizes, 28 active palette blocks and
28 non-skipped palette blocks. The native oracle records the actual frame-header
length; no fixed prefix length is assumed. Default probability tables are
provenance-checked. Cache/descriptor bounds, prefix truncation, exact output
capacity, lease cleanup, source/saved C/Go/direct VM and ASan/UBSan are included.

`build-queue -- sh tests/av1_color_palette.sh` adds 315 encoder-produced color
inputs with 767 active Y and 538 active UV palette blocks, across three depths
and subsampling modes, tiny/odd sizes and dimensions through64. All source
planes match native decoding. `build-queue -- sh
tests/av1_color_palette_boundaries.sh` verifies another164 native-decoded
standard whole frames with every palette size, all ten partition types,
cache reuse, duplicate U entries, both signs/zero V deltas and modular wraps.
It also rejects25 native-rejected portrait4:2:2 partition streams, as required
by the specification's `Subsampled_Size` table. Those invalid frames contribute
no valid-vector coverage counts. Both tests run source/saved IR through C, Go,
direct VM and ASan/UBSan. These bounded tests do not establish full conformance.

`build-queue -- sh tests/av1_key_frames.sh` adds 153 native-decoded full-header
shown-key color inputs at8/10/12 bits, including actual CfL, tiny/odd dimensions,
header-field comparisons, truncation, retained results and plane allocation
failures. `build-queue -- sh tests/av1_key_controls.sh` verifies36 additional
whole frames at all three depths, mono and color, with sequence maxima8/64,
explicit size overrides, frame IDs and equal-interval/decoder-model timing.
These cases compare header state and every source plane against the pinned
native decoder. Their test-only encoder uses the same pinned source in ignored
scratch; it changes no package recipe and is never called by product code.
Both stages run source/saved IR through C, Go, direct VM and ASan/UBSan.

## V02 header contracts

`ParseSequenceHeader(input,begin,end,limits)` consumes one complete sequence
payload and its trailing bits, returning `SequenceHeaderResult`. It describes
profiles 0/1/2, 8/10/12-bit samples, monochrome, color, timing, decoder-model
fields and up to 32 operating points in fixed storage. Dimension and metadata
limits apply before further use. Invalid profile/tool combinations, duplicate
operating points and malformed syntax reject explicitly.

`ParseStillFrameHeader(input,begin,end,sequence,limits,combined=true)` currently
accepts shown KEY pictures with reduced or full headers. It returns a `StillFrameHeaderResult`
with parsed control state and absolute `next` byte position. `combined=true`
validates byte alignment within OBU_FRAME, leaving the tile-group header at
`next`; `false` validates the complete OBU_FRAME_HEADER trailing bits. Parsed
state includes superresolution/render sizes, tile geometry, quantization,
segmentation, lossless flags, deblocking/CDEF/restoration parameters and transform
flags. `ReadTileLayout` uses fixed 65-entry boundary arrays and enforces 64
rows/columns before storing. Full headers also preserve current frame IDs,
order hints, frame/operating-point timing, size override and CDF controls.
KEY pictures use primary-reference NONE, refresh all reference slots and force
integer motion as specified. The experimental entry retains no references;
hidden, inter, intra-only and existing-reference pictures reject explicitly.
Film-grain parameters are bounded and parsed into owned control records.
Parsing other tools' parameters does not imply that reconstruction implements
those tools.

These header APIs expose borrowed input and fixed control records internally.
They do not create references, retain planes, schedule workers or return images.
Retained reference state and general frame entropy remain unfinished V02/V03 work.

`NewTileGroup(input,begin,end,layout,cancellation=null)` and
`NextTileSpan(group*)` provide allocation-free tile-group framing. A cursor
validates explicit group ranges, zero alignment, little-endian tile lengths,
final-tile remainder and cancellation before each span. Spans carry absolute
byte intervals and frame tile indices. Input/token storage must outlive the
cursor. This serial iterator launches no workers and decodes no coefficients.
Its initial local suite is `build-queue -- sh tests/av1_entropy_tiles.sh`;
source/saved C/Go, direct VM and sanitizers cover one-tile groups, lengths,
fragments, malformed/truncated headers and mid-group cancellation. Entropy,
general worker scheduling and repeated full decode remain pending.

Run their local suite with:

```sh
build-queue -- sh tests/av1_headers.sh
```

The default suite requires the pinned dav1d native recipe. It compares 158
sequence headers (146 generated according to the primary AV1 syntax plus 12
sequences extracted from existing AVIF fixtures): 50 fields plus all operating
point/delay parameters, including minimum/maximum legal picture intervals, and
rejects the forbidden saturated interval and invalid monochrome identity
matrix/subsampling combination. It also compares 94 fields in 13 real reduced
still frame headers against dav1d's decoded frame metadata and rejects every
truncated header prefix. These cover existing 8/10/12-bit, color and monochrome
fixtures plus three actual multi-tile lossless/lossy inputs. Actual tile
boundaries and payload spans are compared too. Source and saved IR run in C,
Go and the direct portable interpreter, and native runs use ASan/UBSan.
Header/tile-span parity does not establish authored plane parity for these
larger inputs; the private engine rejects them.

The oracle is dav1d 1.5.4 at revision
`54706fc6bc0cdecab7e9593974a4039cc038fca7`. Tests verify clean tracked source,
the library's `1.5.4-0-g54706fc6` identity and its SHA256. Override its artifact
path with `AV1_DAV1D_LIBRARY` and source with `AV1_DAV1D_SOURCE` if integration
stages the same pinned recipe elsewhere. Local result receipts are written
under ignored `build/scratch/av1{,-headers}/receipt.json` after complete runs.

## Scalar filter references

`deblock.zi` provides allocation-free `FilterDeblockEdge` for input ordered
`p7..p0,q0..q7`. It derives the edge, high-variance and flat masks from scaled
thresholds, then applies the narrow or 6/8/14-sample wide filter. Scheduling and
adaptive threshold selection remain caller responsibilities. Input and threshold
bounds are validated before filtering; failure returns no committed samples.

`build-queue -- sh tests/av1_deblock.sh` passed 3,072 vectors against both
horizontal and vertical pinned libaom scalar functions and an independent
normative reference. It covers 8/10/12-bit samples, enabled/disabled edges,
high variance, flat and wider-flat cases, signed rounding boundaries and 5,136
changed samples. Native oracle guard cells and every inactive product sample
are checked.

`cdef.zi` provides allocation-free `FindCdefDirection` and `FilterCdefBlock`.
The filter consumes a caller-resolved two-pixel halo, uses 30000 only for
unavailable neighbors, and returns a block with stride 8. Center samples must
be real samples. Bounds, source depth, strengths, direction and damping are
validated before filtering; errors and cancellation return no committed samples.
The primary strength accepts the intermediate high-bit-depth values produced
by normative luma variance adjustment.

`build-queue -- sh tests/av1_cdef.sh` passed 768 direction and 1,806 filter
vectors against the pinned libaom scalar functions and an independent reference
of the pinned specification. Coverage includes all eight directions, 8/10/12-bit
samples, four 4/8 block shapes, all 16 missing-halo masks, syntax strengths and
every between-scale primary strength at higher bit depths. The vectors exercise
14,326 changed samples. Malformed input, cancellation and inactive output cells
are verified too.

`wiener.zi` provides allocation-free `FilterWienerBlock` for blocks up to 8x8.
It consumes a caller-resolved three-pixel halo and separate horizontal and
vertical three-tap coefficient sets. It validates the normative tap ranges,
performs horizontal filtering before vertical filtering, and applies the
bit-depth-specific signed rounding and intermediate clipping. Chroma callers
must supply outer tap zero. Output has stride 8 and commits only on success.

`build-queue -- sh tests/av1_wiener.sh` passed 576 vectors against the pinned
libaom scalar function and an independent normative reference, covering
8/10/12-bit samples, all 27 combinations of minimum/zero/maximum taps, random
taps, identity and chroma five-tap filters. The corpus exercises three
intermediate clips and 1,586 final clips, including 1x1 and rectangular blocks.

`sgr.zi` provides allocation-free `FilterSgrBlock` for self-guided restoration
up to 8x8 with the same three-pixel halo contract. It directly computes the
two normative box-filter passes and signed projection with bounded 64-bit
intermediates. All 16 parameter sets are supported. Projection coefficients
use `LrSgrXqd` semantics, including the implicit values for disabled passes.

`build-queue -- sh tests/av1_sgr.sh` passed 1,536 vectors against the pinned
libaom scalar function and an independent normative reference. It covers
all parameter sets, 8/10/12-bit samples, signed projection boundaries, both
single-radius cases, 1x1 and rectangular blocks, 12,240 changed samples and
694 clipped outputs. Invalid implicit coefficients reject explicitly.

These tests pass source and saved IR in C, Go and the direct portable VM, with
ASan/UBSan on generated C. Receipts are saved under ignored
`build/scratch/av1-{deblock,cdef,wiener,sgr}`. These are scalar math tests, not conforming
encoded-frame tests. Frame CDEF scheduling and restoration stripe source selection
remain pending; the authored decoder still rejects unsupported
filtering tools.

`build-queue -- sh tests/av1_filter_kernels.sh` combines the four scalar test
stages. It records source and compiler hashes and rejects changes to those inputs
during its run. Its receipt is separate from the encoded-frame engine suite.

## Film-grain syntax and scaling primitives

`grain_params.zi` provides `ReadStillFilmGrain` for displayed non-inter frames.
It reads from the caller's exact MSB syntax position, checks point counts and
strictly increasing coordinates, enforces the 4:2:0 chroma-pair constraint, and
returns signed AR coefficients. Absence resets all fields. Truncation, malformed
input and cancellation commit no parameters. Inter-frame inheritance is outside
this API's contract.

`build-queue -- sh tests/av1_grain_params.sh` passed 128 parameter streams
produced and read by the pinned unmodified native film-grain syntax functions.
It compares 160 fields and bit positions across mono/420/422/444, every starting
bit position and all four AR lags. It also verifies 5,060 truncated byte prefixes
and 380 count, ordering and chroma-pair mutations. These are authoritative syntax
symbol streams, not encoded-frame conformance vectors.

`grain_scaling.zi` provides caller-owned `NextGrainRandom`, `BuildGrainScaling`
and constant-time `SampleGrainScaling`. It supports zero-point curves, up to
14 sorted points, signed interpolation and the final high-bit-depth lookup bin.
Random state commits only after successful validation and cancellation checks.

`build-queue -- sh tests/av1_grain_scaling.sh` passed 4,096 native random-state
transitions at bit widths 1 through 16, 128 native scaling curves (32,768 table
entries), and 24,576 sampled values across 8/10/12-bit depth. An independent
reference agrees with the native results. Invalid input and cancellation are
covered too. Both grain component tests pass source and saved IR in C, Go and
the direct portable VM, with ASan/UBSan on generated C. Their receipts live under
ignored `build/scratch/av1-grain-{params,scaling}`.

`grain_noise.zi` provides allocation-free `GenerateGrainNoise`. It obtains the
normative Gaussian table once, generates the seeded white noise, applies luma AR
filtering and chroma/luma correlation, and clips to the source-depth grain range.
The owned arrays have stride 82; luma is 82x73 and chroma is 44/82 by 38/73.
Inactive planes and cells are zero. Validation and cancellation failures commit
no arrays.

`build-queue -- sh tests/av1_grain_noise.sh` passed 48 native Gaussian/AR cases
with 861,984 complete-array sample comparisons across mono/420/422/444,
8/10/12-bit depth, every AR lag, grain shift and AR shift, including inactive
planes and independent chroma. Every sample passes source and saved IR in C,
Go and the direct portable VM, with C sanitizers. The corpus is divided into
six programs to respect the portable reader's 100,000-record IR table limit;
large literal comparisons are split into bounded functions.

`grain_apply.zi` provides allocation-free `ApplyFilmGrain64` for borrowed source
planes up to 64x64. It constructs bounded noise stripes, blends horizontal and
vertical block boundaries, scales chroma using original luma, applies signed
chroma mixing and clips active components to full or restricted range, including
the identity-matrix chroma limit. Returned arrays own their samples with stride
64 and zero inactive cells. Inputs remain unchanged; failures commit no output.

`build-queue -- sh tests/av1_grain_apply.sh` passed all 119,208 visible samples
of 48 raw native pictures, including 111,236 changed samples. It covers
mono/420/422/444, 8/10/12-bit depth, 1x1, odd 7x5, 33x35 and 64x64 dimensions,
both overlap states, restricted/full clipping and identity-matrix chroma.
All eight corpus programs pass source/saved C, Go and direct VM plus sanitizers.
Raw native picture parity is separate from encoded-frame decoder parity.

`build-queue -- sh tests/av1_grain_kernels.sh` combines the four grain
component tests and records unchanged source/toolchain fingerprints. Its receipt
is separate from the encoded-frame engine suite.

The private decoder calls these modules for grain-bearing lossless KEY pictures.
`build-queue -- sh tests/av1_grain_frames.sh` passed 48 actual encoded pictures
against the pinned native decoder: 160 grain fields per case and all 119,208
displayed samples. The corpus covers mono/420/422/444, 8/10/12-bit depth and
1x1, 7x5, 33x35 and 64x64 dimensions. All eight corpus programs pass source and
saved IR in C, Go and the direct portable VM, plus C sanitizers. Tests also cover
1,166 truncated prefixes, each of the three output-allocation failures, exact
plane capacities, independent retained outputs and complete worker/scratch
lease cleanup. The fresh engine memory test includes the grain path's scratch.

The shared `DecodeOptions` API currently validates dimensions against an RGBA8
byte floor. Both header parsers validate the sequence maxima, so the private YUV
path currently requires an output cap of at least
`max(aggregate YUV bytes,4*sequence_max_width*sequence_max_height)`, even when a
full header overrides the displayed frame to smaller dimensions. Returned planes contain
only their exact source sample bytes. A reusable dimension-only validator has
been requested upstream; exact raw-YUV cap support is pending that addition.

## Scalar quantization and dequantization

`quantization.zi` provides allocation-free `ResolveQuantizerIndex` for base,
current delta-Q and segment alternate-Q controls, and `GetQuantizationSteps` for
DC/AC lookup with signed seven-bit plane deltas. The 1,536 normative lookup
values in `quant_tables.zi` agree exactly with the pinned specification and
native functions at every depth. The selected table is obtained once for both
DC/AC lookups.

`DequantizeBlock` accepts all nineteen transform sizes. Input coefficients are
the compact row-major `min(width,32) * min(height,32)` signed 20-bit array after
syntax masking. Empty matrix weights select ordinary DC/AC quantizers; otherwise
the caller supplies the selected positive inverse weights for that compact
rectangle. Matrix level, transform-type and lossless gating remain the caller's
responsibility. Products use widened arithmetic, the normative 24-bit magnitude
mask, transform-size division and source-depth clipping. The owned 4,096-cell
result uses the full transform width; cells outside the coded upper-left
rectangle and inactive cells remain zero. Errors and cancellation return no
coefficients. Borrowed inputs remain unchanged.

`build-queue -- sh tests/av1_quantization.sh` passed 98,304 lookup/delta cases and
114 dequantization vectors across 8/10/12-bit depth and all nineteen sizes.
Native inverse-matrix data covers all fifteen active levels and both plane
classes. The normative coefficient reference checks 44,640 compact coefficients
and all 466,944 output cells, including 28,885 product wraps and 41,495 clips.
All twenty corpus programs pass source/saved C, Go and direct VM plus C
sanitizers. Twenty-one forged invalid native slice counts reject null data
before arithmetic/access; a null-data empty matrix succeeds. Fourteen source and
compiler fingerprints remain unchanged during the run.

`build-queue -- sh tests/av1_scalar_kernels.sh` now combines these tests with the
387-vector native/spec WHT corpus and passed. The scalar suite writes its final
receipt only after both components succeed. Quantization is not yet called by
the decoder; lossy tile entropy integration, general inverse transforms and frame
reconstruction remain unfinished. Matrix-data kernel tests are not lossy
encoded-frame conformance tests. Recompute the decoder memory proof when these
records become part of its working state.

## Coefficient scan ordering

`coefficient_scan.zi` provides allocation-free
`BuildCoefficientScan(width,height,mode,cancellation) -> CoefficientScan`.
`ScanDefault` covers all nineteen transform sizes with the normative upper-left
32 coefficient mapping. `ScanRows` and `ScanColumns` cover the nine sizes whose
longest side is at most 16. The result owns forward and inverse 1,024-entry
`u16` maps, the compact coded dimensions and the active count. Inactive entries
remain zero; invalid dimensions/modes and cancellation commit no maps.

The tile caller selects the scan mode from `PlaneTxType`, including selecting
the default scan for transforms with a 64-pixel side before one-dimensional type
mapping. Transform-set legality remains the caller's responsibility. The helper
generates the diagonal, row and column orders directly; product code contains
no native lookup calls or copied scan arrays.

`build-queue -- sh tests/av1_coefficient_scan.sh` passed all 37 normative scans:
9,008 forward positions and 75,776 complete forward/inverse/inactive cells.
Each expected position agrees with both the pinned specification's chapter10
tables and the pinned native arrays after normalizing their transposed storage.
Source/saved C, Go, direct VM and C sanitizers pass, with twelve controlled
source/compiler fingerprints unchanged. Invalid shapes/modes, cancellation and
zero failure outputs are covered too.

`build-queue -- sh tests/av1_entropy_tiles.sh` combines these tests with bounded
tile-group framing/cancellation and the coefficient contexts below, and passed.
Its receipt is written only after all components succeed. General tile entropy and decoder
integration of these scan maps remain unfinished.

## Coefficient entropy contexts

`coefficient_context.zi` provides allocation-free `GetCoefficientContexts` over
borrowed unsigned magnitudes in compact row-major storage. It returns the
selected base or base-eob CDF index and the BR index, using bounded neighbor
reads, magnitude clipping, source transform aspect and AV1 2D/horizontal/vertical
classes. These classes are distinct from the scan-mode constants. The caller
provides a matching scan index/position and validates frame transform legality.
Default contexts cover all nineteen sizes; one-dimensional contexts cover the
nine sizes with longest side at most 16. No CDF, input or decoder state mutates.
Invalid dimensions, positions, classes, slice counts and cancellation return
zero context fields with an error.

`build-queue -- sh tests/av1_coefficient_context.sh` passed 111 native level
planes and 108,096 context-field comparisons at 27,024 positions. Zero,
saturated and seeded-random magnitudes cover all three context classes and
their scan orders. Native functions agree with an independent reference using
the exact pinned specification offset tables. The nineteen corpus programs
pass source/saved C, Go, direct VM and C sanitizers; fourteen controlled
source/compiler fingerprints remain unchanged. Pinned parsing and scan-table
documents have fixed, verified digests. The expanded tile/entropy suite passes
these tests too. General tile decoding and decoder integration remain
unfinished.

## Owned coefficient probabilities

`coefficient_cdfs.zi` provides `NewCoefficientCDFs` with 3,835 owned probability
cells, including independent adaptation counters. The four normative default
categories use the frame's base quantizer, with boundaries at 20, 60 and 120.
Block delta-Q does not select the category. The pinned libaom probability data
retains its copyright, BSD license and patent notice.

`coefficient_cdf_symbols.zi` provides bounded `SelectCoefficientCDF` address
metadata and `ReadCoefficientSymbol`. The latter selects and updates the row
synchronously within the state owner, without returning a borrowed slice.
Seven families cover skip, DC sign, base, base-eob, BR, EOB extra and all seven
EOB areas. BR clamps the transform-size context to 32. Invalid selectors,
factory errors, entropy errors and cancellation return explicit errors.

`build-queue -- sh tests/av1_coefficient_cdfs.sh` passed 6,536 row selections
and 30,680 probability-cell comparisons at eight quantizer boundaries, plus
52 native entropy streams with 3,328 symbols. Final adapted probabilities
agree with libaom; unrelated rows and independent fresh states remain unchanged.
Source and saved IR pass C, Go and the direct VM, with C sanitizers and unchanged
source/compiler fingerprints. These are component symbol streams; general
coefficient integration is described below; encoded-frame integration remains pending.

## General coefficient block syntax

`coefficient_block.zi` provides allocation-free `ReadCoefficientSkip` and
`ReadNonzeroCoefficients`. Keeping them separate lets the caller read luma
transform-type syntax between skip and nonzero coefficients, as required by
the specification. The caller resolves the legal transform class and neighbor
contexts. No transform-type syntax is omitted inside this component.

The reader covers nineteen transform sizes, the permitted 2D/horizontal/vertical
coefficient classes, all EOB areas, reverse base/BR levels, forward signs and
bounded Golomb extensions. It returns owned compact row-major signed quantized
coefficients, cumulative level and DC category. Raw dimensions select entropy
contexts; a 64-pixel side codes only its upper-left 32 coefficients. Errors
return a zero block; consumed entropy/CDF state requires discarding the tile.

`build-queue -- sh tests/av1_coefficient_block.sh` passed 224 streams emitted by
the unmodified pinned `av1_write_coeffs_txb`, covering both plane categories,
all four base-Q probability categories, empty/DC-only/full/random EOBs, signed
levels, the 20-bit mask boundary and disabled adaptation. It compares all
229,376 coefficient cells and 859,040 probability cells, including inactive
storage. Thirty-two seeded arbitrary buffers test deterministic errors and
zero output on failure. Source/saved C, Go, direct VM and C sanitizers pass
with unchanged controlled source/compiler inputs. These are authoritative
coefficient syntax streams, not complete lossy frames. Transform-type syntax,
neighbor scheduling, tile integration and lossy reconstruction remain pending.

`coefficient_neighbors.zi` provides `GetTransformCoefficientContexts` over
caller-selected level and DC edge spans. It computes all thirteen skip contexts
and three DC sign contexts, including chroma's DC-only nonzero edge state.
Spans may end at the frame boundary; missing entries contribute zero. The
function validates transform/residual-block geometry, span lengths, level/DC
ranges and cancellation before returning contexts. It never updates the edge
arrays. `coefficient_geometry.zi` holds the shared bounded size-context mapping.

`build-queue -- sh tests/av1_coefficient_neighbors.sh` passed 5,232 native and
independent specification cases across nineteen transform and twenty-two
residual-block sizes, comparing 10,464 context fields. Coverage includes zero,
small and saturated levels, every sign combination, shortened spans and
invalid dimensions, lengths, levels and signs. Source and saved IR pass C, Go,
the direct VM and C sanitizers. The native oracle packs clipped levels and DC
signs into bytes; the owned implementation keeps the specification's separate
arrays. Tile edge scheduling remains outside this component's coverage.

## Lossy inverse transforms

`inverse_transform.zi` is the scalar AV1 7.13 reference for all nineteen lossy
transform sizes: DCT 4–64, ADST 4–16 and identity 4–32 in both directions,
including the rectangular 1/sqrt2 scaling, `Transform_Row_Shift`, the row/column
clamp ranges and the specification's Hadamard clamps. Intermediates are s64.

`InverseTransform2D(dequant,residual,width,height,tx_type,bit_depth,token)`
reads the row-major `width x height` Dequant array produced by `DequantizeBlock`
and ignores cells outside the upper-left 32x32, as the specification requires.
Inputs must lie in the (BitDepth+8)-bit Dequant range. It writes the unflipped
row-major Residual and may run in place. `AddResidual(samples,stride,residual,...)`
applies the type's vertical/horizontal flips and Clip1 to caller-owned samples.
Any failure clears the residual or leaves the samples unchanged; neither
function allocates. Transform-set legality belongs to `transform_type.zi`;
these kernels accept every computable direction/length combination.

`build-queue -- sh tests/av1_inverse_transform.sh` builds the pinned libaom
forward kernels into a test-only host, transforms bounded residual patterns,
rounds them to dequantizer steps and checks libaom's `av1_inv_txfm2d_add_*_c`
output. An independent Python transcription of 7.13, with its conformance range
checks, must agree with libaom on every pixel. The suite covers 843 conforming
cases across all 185 legal size/type pairs at depths 8/10/12, plus 66 extreme
nonconforming inputs whose deterministic s64 results come from the reference
alone. Boundary cases cover invalid geometry, types and depths, out-of-range
input, aliasing, ignored high-frequency cells, flips, clipping and cancellation.
Source and saved IR run in C, Go and the direct VM, and under ASan/UBSan. This is
not yet called by the frame decoder.

## Reproducible local tests

Run from this package:

```sh
build-queue -- sh tests/av1_obu_range.sh
```

`build-queue -- sh tests/av1_critical_path.sh` runs 22 combined owned stages,
including the filter kernels, grain kernels and encoded-grain frames. Its receipt
records the tested source hashes, six canonical compiler binary hashes and
individual stage receipts under ignored build artifacts. It rejects source/test
or compiler-binary changes during its run. A previous
receipt remains a historical snapshot when later implementation is in progress.

The test requires this package's native libaom recipe and its generated config
headers. It resolves source through `ziran pkg path libaom`, verifies the exact
revision, and links a test-only C host against `build/external/lib/libaom.a`.
`AV1_AOM_SOURCE`, `AV1_AOM_LIBRARY` and `AV1_AOM_CONFIG` may point to the same
verified pinned oracle provided by an integrating build. It uses the canonical
toolchain selected by `tests/common.sh`, including `ZIRAN_ROOT`, and invokes
`build/bin/zi2zx-vm run` directly to avoid native dispatch by the normal launcher.

The deterministic seed `0x415631` covers 192 libaom symbol/CDF cases (10,538
accepted symbols), counters 0/15/16/31/32, update enable/disable, flat and endpoint
CDF cells, short-input overread, 132 integer-oracle syntax cases, 512 randomized
LEB128/OBU boundary cases, and fixed bit-order/length/trailing-bit cases. Another
90 streams (2,190 known symbols) are produced by the pinned upstream entropy
encoder and validate termination, zero padding, corrupted tails and reuse.
Nine
forged invalid native slice counts, including INT64_MIN and INT64_MAX, must
reject a null data pointer before arithmetic or access. Source and saved `.zir`
run in native C, generated Go and the direct portable interpreter. Native C and
the descriptor regression run under ASan/UBSan. Test artifacts and generated
oracle source stay under ignored `build/scratch/av1`.

Random entropy bytes exercise symbol primitives; they are not conforming frame
vectors. Full pinned frame/plane corpus tests are still required before any
authored engine can replace the bridge. No benchmark has been run.

## Specification and provenance

The independent scalar implementation follows the [AV1 bitstream and decoding
process specification](https://aomediacodec.github.io/av1-spec/), pinned for these
tests at revision `5e04f3f75e73a5898d7616c47c52f032144b8f80`:
`04.conventions.md`, `06.bitstream.syntax.md`, `07.bitstream.semantics.md` and
`08.decoding.process.md`, `09.parsing.process.md` in [AOMediaCodec/av1-spec](https://github.com/AOMediaCodec/av1-spec/tree/5e04f3f75e73a5898d7616c47c52f032144b8f80).

The differential oracle is [libaom](https://aomedia.googlesource.com/aom/+/d772e334cc724105040382a977ebb10dfd393293/),
revision `d772e334cc724105040382a977ebb10dfd393293`, using its unmodified
`od_ec_decode_cdf_q15`, `od_ec_dec_tell` and `update_cdf`. It is a pinned
correctness reference, not a current performance comparison. The upstream
source retains its BSD 2-Clause and AOM Patent licenses in its source package;
The named default probability constants, normative Gaussian sequence and quantizer lookup tables are
ported into product codec code, with retained notices and full licenses under
`src/av1`.
