"""Generate a test-only sizeof/offsetof comparison with the pinned C header."""
from pathlib import Path
root=Path(__file__).resolve().parent.parent
out=root/'build/scratch/abi';out.mkdir(parents=True,exist_ok=True)
mapping={
'RawBytes':('avifRWData',{'data':'data','size':'size'}),
'RawTiming':('avifImageTiming',{'timescale':'timescale','pts':'pts','pts_timescale':'ptsInTimescales','duration':'duration','duration_timescale':'durationInTimescales'}),
'RawImage':('avifImage',{'width':'width','height':'height','depth':'depth','format':'yuvFormat','planes':'yuvPlanes','rows':'yuvRowBytes','alpha':'alphaPlane','premultiplied':'alphaPremultiplied','icc':'icc','primaries':'colorPrimaries','transfer':'transferCharacteristics','matrix':'matrixCoefficients','transforms':'transformFlags','aperture':'clap','rotation':'irot','mirror':'imir','exif':'exif','xmp':'xmp','properties':'properties','gain_map':'gainMap'}),
'RawRGB':('avifRGBImage',{'width':'width','depth':'depth','format':'format','avoid_yuv':'avoidLibYUV','premultiplied':'alphaPremultiplied','threads':'maxThreads','pixels':'pixels','row_bytes':'rowBytes'}),
'RawCrop':('avifCropRect',{'x':'x','y':'y','width':'width','height':'height'}),
'RawDecoder':('avifDecoder',{'codec':'codecChoice','threads':'maxThreads','size_limit':'imageSizeLimit','strict':'strictFlags','image':'image','image_index':'imageIndex','image_count':'imageCount','progressive_state':'progressiveState','timing':'imageTiming','timescale':'timescale','duration':'duration','repetitions':'repetitionCount','alpha_present':'alphaPresent'})}
mapping['RawImage'][1].update({'range':'yuvRange','chroma':'yuvChromaSamplePosition','owns_yuv':'imageOwnsYUVPlanes','alpha_row':'alphaRowBytes','owns_alpha':'imageOwnsAlphaPlane','clli':'clli','aspect':'pasp','property_count':'numProperties'})
mapping['RawRGB'][1].update({'height':'height','upsampling':'chromaUpsampling','downsampling':'chromaDownsampling','ignore_alpha':'ignoreAlpha','float_pixels':'isFloat'})
mapping['RawDecoder'][1].update({'source':'requestedSource','progressive':'allowProgressive','incremental':'allowIncremental','ignore_exif':'ignoreExif','ignore_xmp':'ignoreXMP','dimension_limit':'imageDimensionLimit','count_limit':'imageCountLimit','duration_timescale':'durationInTimescales'})
c=['#include <stddef.h>','#include <stdio.h>','#include <avif/avif.h>','int main(void) {']
z=['#import "avif/bridge"','#program_export','main :: () -> s32 {']
for number,(zi,(ctype,fields)) in enumerate(mapping.items()):
    if zi!='RawDecoder':
        c.append(f'printf("%zu\\n", sizeof({ctype}));')
        z.append(f'print("%\\n", size_of({zi}));')
    z.append(f'v{number}: {zi}')
    for field,cf in fields.items():
        c.append(f'printf("%zu\\n", offsetof({ctype}, {cf}));')
        z.append(f'print("%\\n", cast(usize)*v{number}.{field} - cast(usize)*v{number});')
c+=['return 0;','}'];z+=['return 0','}']
(out/'native.c').write_text('\n'.join(c)+'\n')
(out/'abi_contract.zi').write_text('\n'.join(z)+'\n')
