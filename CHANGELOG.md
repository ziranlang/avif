# Changelog

## [Unreleased]

- The native bridge converts 8-bit 4:2:0 and 4:2:2 pictures (BT.601, BT.709, BT.2020, FCC and SMPTE 240; full or limited range) to RGBA itself, split across the cores. It repeats libavif's float arithmetic for centred bilinear chroma in the same order, so every byte matches libavif and the reference decoder's digests. Built without libyuv, libavif's generic loop was most of a phone's decode. 4:4:4 keeps libavif's own fast path.
- Add bounded still-image AVIF encoding with quality 35 by default, lossless alpha, metadata and orientation preservation, and explicit Lanczos RGBA previews.
- Native artifact project tools prepare pinned Meson and Ninja on fresh consumers.
- Headless AVIF APIs and command, bounded container policy and pinned native libavif/libaom artifacts with verification fixtures.
- dav1d is the default engine, with its runtime-dispatched assembly and a measured bounded thread policy; libaom stays the explicit oracle, and every target converts bit-exactly.
- The authored AV1 decoder moved to the new av1 package, which avif now depends on.
- libaom, the oracle engine, is pinned at 3.15.3.
- Tests run bundles on the portable VM with `zi2zx run --vm`.
