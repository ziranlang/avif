# Generated AVIF regression fixtures

Tiny patterns are copied byte-for-byte from Kryon's generated fixtures, under
its BSD-3-Clause license (retained in the package LICENSE). The source patterns
and independent Pillow geometry appear in `tests/generate_fixtures.py`.
Original encoding used official libavif avifenc1.2.1 with CPU libaom. The
`.rgba` files are independently generated expected input/geometry bytes; `.txt`
records dimensions and the original allowed conversion tolerance.

`.strict.rgba` files capture the read-only current Kryon decode implementation
with pinned libavif1.3.0/libaom3.13.1, so this package verifies exact extraction
parity, including high-depth rounding and premultiplication. `baseline.sha256`
records the actual source and static library digests used for that capture.
These tiny golden files are saved binary assets, not regenerated during tests.
`manifest.json` pins all input/golden/text fixture digests. Ordinary tests fetch
nothing and do not need a Kryon checkout.

Cases: 8/10/12-bit RGBA and monochrome, opaque/transparent/premultiplied alpha,
all four rotations and both mirrors after clean aperture, two-frame first-frame
decode, invalid crop, malformed/truncated containers and image size limits.
This is regression parity, not a full AV1/AVIF conformance corpus.

Explicit regeneration (review and repin digests afterwards):

```sh
AVIFENC=/path/to/avifenc python3 tests/generate_fixtures.py
build-queue -- env KRYON_ROOT=/path/to/canonical/kryon sh tests/pin_goldens.sh
```

The owner's Jungle title asset is deliberately excluded from the distributable
corpus; redistribution rights are unverified. It can be an optional local
comparison using the original file, outside mandatory package fixtures.
