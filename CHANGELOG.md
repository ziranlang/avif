# Changelog

## [Unreleased]

- The native bridge converts 8-bit pictures (4:2:0, 4:2:2, 4:4:4; BT.601, BT.709, BT.2020; full or limited range) to RGBA itself: libavif's centred bilinear chroma in fixed point, split across the cores, within one level of the reference. Built without libyuv, libavif's float path was most of a phone's decode.
- Add bounded still-image AVIF encoding with quality 35 by default, lossless alpha, metadata and orientation preservation, and explicit Lanczos RGBA previews.
- Native artifact project tools prepare pinned Meson and Ninja on fresh consumers.
- Headless AVIF APIs and command, bounded container policy and pinned native libavif/libaom artifacts with verification fixtures.
- dav1d is the default engine, with its runtime-dispatched assembly and a measured bounded thread policy; libaom stays the explicit oracle, and every target converts bit-exactly.
- The authored AV1 decoder moved to the new av1 package, which avif now depends on.
- libaom, the oracle engine, is pinned at 3.15.3.
- Tests run bundles on the portable VM with `zi2zx run --vm`.
