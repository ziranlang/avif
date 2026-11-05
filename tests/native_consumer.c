/* Test-only consumer of the package-owned static CMake target. */
#include <avif/avif.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int decode(avifCodecChoice codec, int threads, const unsigned char *input, size_t size,
                  const unsigned char *expected, size_t count)
{
    avifDecoder *decoder = avifDecoderCreate();
    if (!decoder) return 3;
    decoder->codecChoice = codec;
    decoder->maxThreads = threads;
    if (avifDecoderSetIOMemory(decoder, input, size) || avifDecoderParse(decoder) || avifDecoderNextImage(decoder)) return 4;
    avifRGBImage rgb;
    avifRGBImageSetDefaults(&rgb, decoder->image);
    rgb.depth = 8; rgb.format = AVIF_RGB_FORMAT_RGBA; rgb.maxThreads = threads;
    if (avifRGBImageAllocatePixels(&rgb) || avifImageYUVToRGB(decoder->image, &rgb)) return 5;
    int invalid = count != (size_t)rgb.width * rgb.height * 4;
    for (unsigned y = 0; !invalid && y < rgb.height; ++y)
        invalid = memcmp(rgb.pixels + y * rgb.rowBytes, expected + y * rgb.width * 4, rgb.width * 4) != 0;
    avifRGBImageFreePixels(&rgb);
    avifDecoderDestroy(decoder);
    return invalid ? 6 : 0;
}

int main(int argc, char **argv)
{
    if (argc != 3 || strcmp(avifVersion(), "1.3.0") ||
        !avifCodecName(AVIF_CODEC_CHOICE_AOM, AVIF_CODEC_FLAG_CAN_DECODE) ||
        avifCodecName(AVIF_CODEC_CHOICE_AOM, AVIF_CODEC_FLAG_CAN_ENCODE) ||
        !avifCodecName(AVIF_CODEC_CHOICE_DAV1D, AVIF_CODEC_FLAG_CAN_DECODE) ||
        avifCodecName(AVIF_CODEC_CHOICE_AUTO, AVIF_CODEC_FLAG_CAN_ENCODE)) return 1;
    unsigned char input[4096], expected[4096];
    FILE *source = fopen(argv[1], "rb"), *golden = fopen(argv[2], "rb");
    if (!source || !golden) return 2;
    size_t size = fread(input, 1, sizeof(input), source);
    size_t count = fread(expected, 1, sizeof(expected), golden);
    fclose(source); fclose(golden);
    /* The libaom oracle and the dav1d default (single and threaded) must be
     * byte-identical to the same strict golden. */
    int status = decode(AVIF_CODEC_CHOICE_AOM, 1, input, size, expected, count);
    if (!status) status = decode(AVIF_CODEC_CHOICE_DAV1D, 1, input, size, expected, count);
    if (!status) status = decode(AVIF_CODEC_CHOICE_DAV1D, 8, input, size, expected, count);
    if (status) return status;
    puts("Reusable static CMake target: pinned decoder-only libavif with libaom oracle and dav1d default exact golden passed");
    return 0;
}
