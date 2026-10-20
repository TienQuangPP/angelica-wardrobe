"""Extract the textures of a .glb (RGB and alpha as separate PNGs) and print material info.

py glb_tex.py file.glb outprefix
"""
import io
import json
import struct
import sys

from PIL import Image

data = open(sys.argv[1], 'rb').read()
prefix = sys.argv[2]
js_len = struct.unpack_from('<I', data, 12)[0]
gltf = json.loads(data[20:20 + js_len])
bin_off = 20 + js_len + 8
for i, m in enumerate(gltf.get('materials', [])):
    print('material', i, json.dumps(m, ensure_ascii=False)[:300])
for i, img in enumerate(gltf.get('images', [])):
    bv = gltf['bufferViews'][img['bufferView']]
    raw = data[bin_off + bv.get('byteOffset', 0): bin_off + bv.get('byteOffset', 0) + bv['byteLength']]
    im = Image.open(io.BytesIO(raw))
    im.load()
    print('image', i, img.get('name'), img.get('mimeType'), im.size, im.mode)
    rgba = im.convert('RGBA')
    rgba.convert('RGB').save(f'{prefix}_{i}_rgb.png')
    rgba.getchannel('A').save(f'{prefix}_{i}_a.png')
    a = rgba.getchannel('A')
    hist = a.histogram()
    print('   alpha: min', min(i for i, v in enumerate(hist) if v), 'max', max(i for i, v in enumerate(hist) if v),
          'share>128', round(sum(hist[129:]) / sum(hist), 3))
