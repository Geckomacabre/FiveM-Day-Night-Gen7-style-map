"""Draws the minimap vector tiles into the 2D map tiles' pixel space.

The 2D tiles are a 2 x 3 grid of 4500 m squares whose top-left corner is
world (-4140, 8400): tile minimap[_sea]_<row>_<col> covers
x -4140 + 4500*col .. +4500 and y 8400 - 4500*row .. -4500 (row 0 is the
north). Checked by drawing the vectors over Gen7's own 2D tiles: they line up.

The vectors are drawn ground ("back") first, then the foreground pieces,
deeper z under higher z; the vector sea is left out (the big map does not
draw it either).
"""
import glob
import os
import tempfile

import numpy as np
from PIL import Image, ImageDraw

from vectors import dump, joaat

TILE_M = 4500.0
START_X, START_Y = -4140.0, 8400.0


def tile_rect(row, col):
    x0 = START_X + TILE_M * col
    y1 = START_Y - TILE_M * row
    return x0, y1 - TILE_M, x0 + TILE_M, y1


def load_triangles(vector_dir, cache_dir=None):
    """Every ground and foreground triangle in the vector tiles, as
    (corners (T,3,2) world x,y; colour (T,4) uint8; layer (T,) sort key)."""
    corners, colours, layers = [], [], []
    tmp = tempfile.TemporaryDirectory() if cache_dir is None else None
    cache_dir = cache_dir or tmp.name
    for path in sorted(glob.glob(os.path.join(vector_dir, 'minimap_*_*.ydd'))):
        col, row = (int(v) for v in os.path.basename(path)[8:-4].split('_'))
        mesh = dump(path, os.path.join(cache_dir, os.path.basename(path) + '.bin'))
        back = joaat(f'supertile_back_{col}_{row}')
        sea = joaat(f'supertile_sea_{col}_{row}')
        for h, geoms in mesh.items():
            if h == sea:
                continue
            for pos, col_rgba, tri in geoms:
                if len(tri) == 0:
                    continue
                corners.append(pos[tri][:, :, :2])
                # ground first (pass 0), then foregrounds by height
                z = pos[tri][:, :, 2].mean(1)
                layers.append(np.where(h == back, -100.0, z))
                # a triangle takes its first corner's colour: every corner of a
                # minimap triangle is the same flat colour
                colours.append(col_rgba[tri[:, 0]])
    if tmp:
        tmp.cleanup()
    return np.concatenate(corners), np.concatenate(colours), np.concatenate(layers)


def draw_tile(tris, row, col, size, supersample=2):
    """The vectors over one 2D tile, (size,size,4) uint8 RGBA, transparent
    where there are none. Antialiased by drawing `supersample` times larger."""
    corners, colours, layers = tris
    x0, y0, x1, y1 = tile_rect(row, col)
    n = size * supersample
    inside = ((corners[:, :, 0].max(1) >= x0) & (corners[:, :, 0].min(1) <= x1) &
              (corners[:, :, 1].max(1) >= y0) & (corners[:, :, 1].min(1) <= y1))
    order = np.argsort(layers[inside], kind='stable')
    c = corners[inside][order]
    rgba = colours[inside][order]
    px = (c[:, :, 0] - x0) / TILE_M * n
    py = (y1 - c[:, :, 1]) / TILE_M * n

    img = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i in range(len(c)):
        d.polygon([(px[i, 0], py[i, 0]), (px[i, 1], py[i, 1]), (px[i, 2], py[i, 2])],
                  fill=tuple(int(v) for v in rgba[i]))
    a = np.asarray(img).astype(np.float32)
    if supersample > 1:
        # premultiplied box filter down to `size`
        a = a.reshape(size, supersample, size, supersample, 4)
        alpha = a[..., 3].mean((1, 3))
        rgb = (a[..., :3] * a[..., 3:4]).sum((1, 3)) / np.maximum(a[..., 3].sum((1, 3)), 1e-6)[..., None]
        a = np.dstack([rgb, alpha])
    return np.clip(np.rint(a), 0, 255).astype(np.uint8)


def match_colours(tris, rasters, size=1024):
    """The vectors' colours are not the 2D tiles' colours (the airport's ground
    is a warm grey in the vectors and a cool one in the tiles, and so on), so
    drawing the vectors as they are would change the map's colours, not just
    sharpen it. For each vector colour this finds what the 2D tiles show where
    that colour is drawn (the median, away from any edge), and returns the
    triangles recoloured to it.
    `rasters`: {(row, col): (size,size,4) uint8} -- the 2D tiles to match."""
    corners, colours, layers = tris
    palette, label = np.unique(colours, axis=0, return_inverse=True)
    label = label.reshape(-1)
    samples = [[] for _ in palette]
    for (row, col), ras in rasters.items():
        x0, y0, x1, y1 = tile_rect(row, col)
        inside = ((corners[:, :, 0].max(1) >= x0) & (corners[:, :, 0].min(1) <= x1) &
                  (corners[:, :, 1].max(1) >= y0) & (corners[:, :, 1].min(1) <= y1))
        idx = np.nonzero(inside)[0][np.argsort(layers[inside], kind='stable')]
        img = Image.new('I', (size, size), -1)
        d = ImageDraw.Draw(img)
        for i in idx:
            c = corners[i]
            d.polygon([((c[k, 0] - x0) / TILE_M * size, (y1 - c[k, 1]) / TILE_M * size) for k in range(3)],
                      fill=int(label[i]))
        lab = np.asarray(img)
        # keep pixels whose whole 5x5 neighbourhood is the same colour
        solid = lab >= 0
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                solid &= np.roll(np.roll(lab, dy, 0), dx, 1) == lab
        solid &= ras[..., 3] == 255
        for p in np.unique(lab[solid]):
            samples[p].append(ras[..., :3][solid & (lab == p)])
    mapped = palette.copy()
    for p in range(len(palette)):
        px = np.concatenate(samples[p]) if samples[p] else np.zeros((0, 3))
        if len(px) >= 50:
            mapped[p, :3] = np.median(px, axis=0)
    return (corners, mapped[label], layers), {tuple(int(v) for v in palette[p]): tuple(int(v) for v in mapped[p])
                                              for p in range(len(palette))}


def over(top, base):
    """`top` composited over `base`, both (H,W,4) uint8 straight alpha."""
    t = top.astype(np.float32) / 255
    b = base.astype(np.float32) / 255
    ta, ba = t[..., 3:4], b[..., 3:4]
    oa = ta + ba * (1 - ta)
    rgb = (t[..., :3] * ta + b[..., :3] * ba * (1 - ta)) / np.maximum(oa, 1e-6)
    return np.clip(np.rint(np.dstack([rgb, oa]) * 255), 0, 255).astype(np.uint8)


def upscale(rgba, size):
    """Lanczos upscale with alpha handled premultiplied, so transparent texels'
    colour does not bleed into the edges."""
    a = rgba.astype(np.float32)
    alpha = a[..., 3:4] / 255
    pm = Image.fromarray(np.clip(np.rint(np.dstack([a[..., :3] * alpha, a[..., 3:4]])), 0, 255).astype(np.uint8))
    up = np.asarray(pm.resize((size, size), Image.LANCZOS)).astype(np.float32)
    straight = np.asarray(Image.fromarray(rgba[..., :3]).resize((size, size), Image.LANCZOS)).astype(np.float32)
    ua = up[..., 3:4] / 255
    rgb = np.where(ua > 1e-3, up[..., :3] / np.maximum(ua, 1e-3), straight)
    return np.clip(np.rint(np.dstack([rgb, up[..., 3:4]])), 0, 255).astype(np.uint8)
