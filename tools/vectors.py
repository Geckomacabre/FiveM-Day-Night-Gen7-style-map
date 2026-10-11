"""Reads the minimap vector tiles (minimap_X_Y.ydd) as triangles.

The game draws these when the big map is zoomed in (and on the radar). Each
.ydd is one "supertile" and holds named drawables (the names are only stored
as hashes, so they are matched by hashing the expected names):
  supertile_back_<col>_<row>                 the ground, drawn first
  supertile_sea_<col>_<row>                  sea (not drawn on the big map)
  supertile_fore_<col>_<row>_tile_<j>_<i>    roads, buildings... on top
Every vertex is a position and a colour; there are no textures.

`ytdtool yddmesh` writes the raw vertex/index data this module reads.
"""
import os
import struct
import subprocess

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
YTDTOOL = os.path.join(HERE, 'ytdtool', 'bin', 'Release', 'net8.0', 'ytdtool.exe')


def joaat(s):
    h = 0
    for c in s.lower().encode():
        h = (h + c) & 0xFFFFFFFF
        h = (h + (h << 10)) & 0xFFFFFFFF
        h ^= h >> 6
    h = (h + (h << 3)) & 0xFFFFFFFF
    h ^= h >> 11
    h = (h + (h << 15)) & 0xFFFFFFFF
    return h


def read_mesh(path):
    """{nameHash: [ (positions (N,3) float32, colours (N,4) uint8 RGBA, triangles (M,3) int) ]}"""
    out = {}
    with open(path, 'rb') as f:
        data = f.read()
    off = 0

    def u32():
        nonlocal off
        v = struct.unpack_from('<I', data, off)[0]
        off += 4
        return v

    for _ in range(u32()):
        h, ng = u32(), u32()
        geoms = []
        for _ in range(ng):
            vc, stride, flags, ic = u32(), u32(), u32(), u32()
            vb = np.frombuffer(data, np.uint8, vc * stride, off).reshape(vc, stride)
            off += vc * stride
            ib = np.frombuffer(data, np.uint16, ic, off).astype(np.int64)
            off += ic * 2
            if flags != 17 or stride != 16:
                raise ValueError(f'{path}: unexpected vertex layout flags={flags} stride={stride}')
            pos = vb[:, 0:12].copy().view(np.float32).reshape(vc, 3)
            # colour0 is stored B,G,R,A
            col = vb[:, 12:16][:, [2, 1, 0, 3]].copy()
            geoms.append((pos, col, ib.reshape(-1, 3)))
        out[h] = geoms
    return out


def dump(ydd, out_bin):
    subprocess.run([YTDTOOL, 'yddmesh', ydd, out_bin], check=True, capture_output=True)
    return read_mesh(out_bin)


if __name__ == '__main__':
    import sys
    m = dump(sys.argv[1], sys.argv[2])
    col, row = (int(v) for v in os.path.basename(sys.argv[1])[8:-4].split('_'))
    names = {joaat(f'supertile_back_{col}_{row}'): 'back', joaat(f'supertile_sea_{col}_{row}'): 'sea'}
    for i in range(8):
        for j in range(8):
            names[joaat(f'supertile_fore_{col}_{row}_tile_{j}_{i}')] = f'fore_{j}_{i}'
    for h, geoms in m.items():
        for pos, c, tri in geoms:
            uniq = np.unique(c, axis=0)
            print(f'{names.get(h, hex(h)):10} verts={len(pos):6} tris={len(tri):6} '
                  f'x {pos[:, 0].min():8.1f}..{pos[:, 0].max():8.1f}  y {pos[:, 1].min():8.1f}..{pos[:, 1].max():8.1f}  '
                  f'z {pos[:, 2].min():6.2f}..{pos[:, 2].max():6.2f}  colours={len(uniq)} e.g. {[tuple(int(x) for x in u) for u in uniq[:4]]}')
