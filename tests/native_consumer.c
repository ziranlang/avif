/* Test-only consumer of the package-owned static CMake target. */
#include <avif/avif.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv)
{
    if (argc != 3 || strcmp(avifVersion(), "1.3.0") ||
        !avifCodecName(AVIF_CODEC_CHOICE_AOM, AVIF_CODEC_FLAG_CAN_DECODE) ||
        avifCodecName(AVIF_CODEC_CHOICE_AOM, AVIF_CODEC_FLAG_CAN_ENCODE)) return 1;
    unsigned char input[4096], expected[4096];
    FILE *source = fopen(argv[1], "rb"), *golden = fopen(argv[2], "rb");
    if (!source || !golden) return 2;
    size_t size = fread(input, 1, sizeof(input), source);
    size_t count = fread(expected, 1, sizeof(expected), golden);
    fclose(source); fclose(golden);
    avifDecoder *decoder = avifDecoderCreate();
    if (!decoder) return 3;
    decoder->codecChoice = AVIF_CODEC_CHOICE_AOM;
    decoder->maxThreads = 1;
    if (avifDecoderSetIOMemory(decoder, input, size) || avifDecoderParse(decoder) || avifDecoderNextImage(decoder)) return 4;
    avifRGBImage rgb;
    avifRGBImageSetDefaults(&rgb, decoder->image);
    rgb.depth = 8; rgb.format = AVIF_RGB_FORMAT_RGBA; rgb.maxThreads = 1;
    if (avifRGBImageAllocatePixels(&rgb) || avifImageYUVToRGB(decoder->image, &rgb)) return 5;
    int invalid = count != (size_t)rgb.width * rgb.height * 4;
    for (unsigned y = 0; !invalid && y < rgb.height; ++y)
        invalid = memcmp(rgb.pixels + y * rgb.rowBytes, expected + y * rgb.width * 4, rgb.width * 4) != 0;
    avifRGBImageFreePixels(&rgb);
    avifDecoderDestroy(decoder);
    if (invalid) return 6;
    puts("Reusable static CMake target: pinned decoder-only libavif/AOM exact golden passed");
    return 0;
}
