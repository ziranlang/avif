"""Independent direct 2D Lanczos-3 oracle for the separable kernel."""
import math
from pathlib import Path
import sys

def weight(x):
    if abs(x) < 1e-12: return 1.0
    if abs(x) >= 3: return 0.0
    return math.sin(math.pi*x)*math.sin(math.pi*x/3)*3/(math.pi*x)**2

def byte(x): return max(0,min(255,int(x+0.5)))

def reference(width,height):
    source = [[[(x*43+y*11)%256,(x*13+y*61)%256,(x*71+y*23)%256,(x*29+y*47)%256] for x in range(7)] for y in range(5)]
    result = bytearray()
    scale_x,scale_y = 7/width,5/height
    fx,fy = max(1,scale_x),max(1,scale_y)
    for y in range(height):
        cy = (y+0.5)*scale_y-0.5
        for x in range(width):
            cx = (x+0.5)*scale_x-0.5
            sums,total = [0.0]*4,0.0
            for sy in range(math.floor(cy-3*fy)+1,math.floor(cy+3*fy)+1):
                for sx in range(math.floor(cx-3*fx)+1,math.floor(cx+3*fx)+1):
                    w = weight((sy-cy)/fy)*weight((sx-cx)/fx)
                    p = source[max(0,min(4,sy))][max(0,min(6,sx))]
                    for ch in range(3): sums[ch] += p[ch]*p[3]/255*w
                    sums[3] += p[3]*w
                    total += w
            alpha = sums[3]/total
            result.extend([byte(sums[ch]/total*255/alpha) if alpha > 0 else 0 for ch in range(3)]+[byte(alpha)])
    return bytes(result)

for width,height in [(3,2),(11,9)]:
    expected = reference(width,height)
    actual = (Path(sys.argv[1])/f'preview-{width}x{height}.rgba').read_bytes()
    assert len(actual) == len(expected)
    assert max(abs(a-b) for a,b in zip(actual,expected)) <= 1
print('Lanczos matches independent 2D oracle: downscale/upscale, <=1 byte rounding')
