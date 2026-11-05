/* Test oracle only: pinned libavif converts independent synthetic YUV planes
 * through its public scalar straight RGBA8 path, with explicit chroma filter. */
#include <avif/avif.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static void sample(uint8_t *p, unsigned depth, unsigned value) {
    p[0] = (uint8_t)value;
    if (depth > 8) p[1] = (uint8_t)(value >> 8);
}
static unsigned load(const uint8_t *p, unsigned depth) { return p[0] | (depth > 8 ? (unsigned)p[1] << 8 : 0); }
static void plane(const uint8_t *p, unsigned width, unsigned height, unsigned stride, unsigned depth) {
    unsigned bytes = depth > 8 ? 2 : 1;
    for (unsigned y=0; y<height; ++y) {
        for (unsigned x=0; x<width*bytes; ++x) printf("%02x",p[y*stride+x]);
        /* Padded little-endian fixture deliberately differs from native rows. */
        if (y+1<height) printf("4d4d4d");
    }
    puts("");
}
int main(void) {
    if (strcmp(avifVersion(),"1.3.0")) return 1;
    unsigned matrices[] = {0,1,5,6,9,2};
    for (unsigned depth=8; depth<=12; depth+=2)
    for (unsigned full=0; full<=1; ++full)
    for (unsigned mi=0; mi<6; ++mi)
    for (unsigned format=AVIF_PIXEL_FORMAT_YUV444; format<=AVIF_PIXEL_FORMAT_YUV400; ++format)
    for (unsigned alpha=0; alpha<=2; ++alpha)
    for (unsigned filter=0; filter<=1; ++filter) {
        if (matrices[mi]==0 && format!=AVIF_PIXEL_FORMAT_YUV444 && format!=AVIF_PIXEL_FORMAT_YUV400) continue;
        if (matrices[mi]==2 && format!=AVIF_PIXEL_FORMAT_YUV400) continue;
        if (filter && (format==AVIF_PIXEL_FORMAT_YUV444 || format==AVIF_PIXEL_FORMAT_YUV400)) continue;
        const unsigned w=7,h=5,max=(1u<<depth)-1,bytes=depth>8?2:1;
        avifImage *image=avifImageCreate(w,h,depth,(avifPixelFormat)format);
        image->yuvRange=full?AVIF_RANGE_FULL:AVIF_RANGE_LIMITED;
        image->matrixCoefficients=(avifMatrixCoefficients)matrices[mi];
        image->alphaPremultiplied=alpha==2;
        if (avifImageAllocatePlanes(image,AVIF_PLANES_YUV|(alpha?AVIF_PLANES_A:0))) return 2;
        avifPixelFormatInfo info; avifGetPixelFormatInfo(image->yuvFormat,&info);
        for (unsigned c=0;c<3;++c) {
            if (c && format==AVIF_PIXEL_FORMAT_YUV400) continue;
            unsigned pw=c?(w+info.chromaShiftX)>>info.chromaShiftX:w;
            unsigned ph=c?(h+info.chromaShiftY)>>info.chromaShiftY:h;
            for (unsigned y=0;y<ph;++y) for(unsigned x=0;x<pw;++x)
                sample(image->yuvPlanes[c]+y*image->yuvRowBytes[c]+x*bytes,depth,
                       ((x*113+y*67+c*31+x*y*7)*(max+1)/256)&max);
        }
        if(alpha) for(unsigned y=0;y<h;++y) for(unsigned x=0;x<w;++x) {
            unsigned values[]={0,1,max/2,max,max/3};
            sample(image->alphaPlane+y*image->alphaRowBytes+x*bytes,depth,values[(x+y)%5]);
        }
        avifRGBImage rgb; avifRGBImageSetDefaults(&rgb,image);
        rgb.depth=8; rgb.format=AVIF_RGB_FORMAT_RGBA;
        rgb.avoidLibYUV=AVIF_TRUE; rgb.maxThreads=1; rgb.alphaPremultiplied=AVIF_FALSE;
        rgb.chromaUpsampling=filter?AVIF_CHROMA_UPSAMPLING_BILINEAR:AVIF_CHROMA_UPSAMPLING_NEAREST;
        if(avifRGBImageAllocatePixels(&rgb)||avifImageYUVToRGB(image,&rgb)) return 3;
        printf("%u %u %u %u %u %u %u %u\n",depth,full,matrices[mi],info.chromaShiftX,info.chromaShiftY,format==AVIF_PIXEL_FORMAT_YUV400,alpha,filter);
        plane(image->yuvPlanes[0],w,h,image->yuvRowBytes[0],depth);
        for(unsigned c=1;c<3;++c) {
            if(format==AVIF_PIXEL_FORMAT_YUV400) puts("");
            else plane(image->yuvPlanes[c],(w+info.chromaShiftX)>>info.chromaShiftX,(h+info.chromaShiftY)>>info.chromaShiftY,image->yuvRowBytes[c],depth);
        }
        if(alpha) plane(image->alphaPlane,w,h,image->alphaRowBytes,depth); else puts("");
        for(unsigned y=0;y<h;++y) for(unsigned x=0;x<w;++x) {
            uint8_t *p=rgb.pixels+y*rgb.rowBytes+x*4;
            unsigned a=alpha?(load(image->alphaPlane+y*image->alphaRowBytes+x*bytes,depth)*255+max/2)/max:255;
            printf("%02x%02x%02x%02x",p[0],p[1],p[2],a);
        }
        puts(""); avifRGBImageFreePixels(&rgb); avifImageDestroy(image);
    }
    return 0;
}
