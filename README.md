# AVIF

Optional, headless Ziran image package. Handwritten decoder policy, transforms,
API and CLI are `.zi`. The initial AV1/container decoding engine is a pinned
external libavif bridge; this is not an authored AV1 decoder or a speed claim.
No Kryon, window system, browser, or GUI library is required.

```zi
#import "avif/api"
options := DefaultOptions()
result := Decode(BorrowBytes(bytes), options)
// Check result.is_ok before using result.image, an owned std/image.Image.
```

From a consumer, add `https://github.com/ziranlang/avif.git` with `ziran add`.
The manifest pins libavif, libaom and optional dav1d source packages. Local
canonical checkout overrides belong in ignored `ziran.local.toml`. Production lockfiles resolve committed package and toolchain revisions.

Run the package suite in this checkout:

```sh
build-queue -- sh tests/avif.sh
build-queue -- sh tests/bmff.sh
```

The test harness uses the canonical sibling Ziran checkout when available;
otherwise set `ZIRAN_ROOT` to a built current toolchain. It builds a real
consumer of this package, resolves its exports and requests its native artifact
through `ziran pkg artifact avif:native --platform linux-x86_64-gnu`.
Standalone module-path tests additionally verify source and saved `.zir`.

The stable headless command produced by the suite is:

```sh
build/bin/avif tests/fixtures/rgba8.avif build/output.rgba
```

It writes tight straight-alpha RGBA8 and prints dimensions, source depth,
source frame count and alpha presence. Errors have stable shared error codes.
See [implementation and verification status](docs/VERIFICATION.md),
[API](docs/API.md), [native recipe](native/README.md) and
[fixture provenance](tests/fixtures/README.md).
