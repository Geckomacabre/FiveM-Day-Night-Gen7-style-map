"""Builds the Gen7 map tiles, day and night, for this resource (gen7_map/stream).

  python build.py            # writes ../stream (this resource's) + out/ previews
  python build.py --out DIR  # somewhere else

Inputs (source/, not in git -- the mod's own files, see README):
  source/gen7_tiles/    Gen7's 2D tiles: minimap[_sea]_<r>_<c>.ytd, minimap_lod_128.ytd
  source/gen7_vectors/  Gen7's vector tiles: minimap_<c>_<r>.ydd (its minimap.rpf)

What gets written, per 2D tile (row r 0-2, column c 0-1):
  minimap_sea_<r>_<c>.ytd       the big map's tile, by day      3072, DXT5
  gen7night_sea_<r>_<c>.ytd     the same at night               3072, DXT5
  minimap_<r>_<c>.ytd           the radar's tile, by day        3072, DXT1
  gen7night_<r>_<c>.ytd         the same at night               3072, DXT1
and minimap_lod_128.ytd / gen7night_lod_128.ytd (the radar's far overview).

Gen7's own 2D tiles are 1024 square; the mod relies on its vector tiles for
everything zoomed in. This port is made for a map with no vector tiles
(ls_map_lite streams empty ones and draws everything from 2D tiles at 3072),
so each
3072 tile is Gen7's 2D tile enlarged with Gen7's vectors drawn over it sharp,
recoloured to the 2D tiles' own colours (raster.match_colours). The night
tiles are the day ones through nightcolor.night(). Texture names inside the
night files are the game's (minimap_sea_0_0 ...), which is what
AddReplaceTexture swaps between (see gen7_map/client.lua).
"""
import argparse
import os
import shutil
import sys
import time

import numpy as np
from PIL import Image

import raster
import tiles
from nightcolor import night

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'source')
RESOURCE = os.path.normpath(os.path.join(HERE, '..', 'stream'))
SIZE = 3072
NIGHT_PREFIX = 'gen7night'

SETS = [
    # (game prefix, night prefix, format)
    ('minimap_sea', f'{NIGHT_PREFIX}_sea', 'DXT5'),   # the big (pause) map draws these
    ('minimap', NIGHT_PREFIX, 'DXT1'),                # the radar, zoomed out / expanded
]


def to_night(rgba):
    return np.dstack([night(rgba[..., :3]), rgba[..., 3]])


def preview(day_tiles, night_tiles, out_dir, sea_rgb_day, sea_rgb_night):
    """The big map as a whole, day and night, over a plain sea colour, plus a
    full-size crop of downtown."""
    def stitch(tile_map, bg):
        canvas = Image.new('RGBA', (2 * SIZE, 3 * SIZE), bg + (255,))
        for (r, c), t in tile_map.items():
            canvas.alpha_composite(Image.fromarray(t), (c * SIZE, r * SIZE))
        return canvas.convert('RGB')
    day, nite = stitch(day_tiles, sea_rgb_day), stitch(night_tiles, sea_rgb_night)
    w = 700
    h = int(day.size[1] * w / day.size[0])
    side = Image.new('RGB', (2 * w + 12, h), (255, 255, 255))
    side.paste(day.resize((w, h), Image.LANCZOS), (0, 0))
    side.paste(nite.resize((w, h), Image.LANCZOS), (w + 12, 0))
    side.save(os.path.join(out_dir, 'bigmap_day_night.jpg'), quality=90)
    box = (int(0.36 * 2 * SIZE), int(0.705 * 3 * SIZE), int(0.36 * 2 * SIZE) + 1100, int(0.705 * 3 * SIZE) + 800)
    pair = Image.new('RGB', (2 * 1100 + 12, 800), (255, 255, 255))
    pair.paste(day.crop(box), (0, 0))
    pair.paste(nite.crop(box), (1100 + 12, 0))
    pair.save(os.path.join(out_dir, 'downtown_day_night.jpg'), quality=92)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=RESOURCE)
    ap.add_argument('--previews', default=os.path.join(HERE, 'out'))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.previews, exist_ok=True)
    t0 = time.time()

    tris = raster.load_triangles(os.path.join(SRC, 'gen7_vectors'))
    print(f'{len(tris[0])} vector triangles')

    keep_for_preview = {}
    for game, nite, fmt in SETS:
        base = {(r, c): tiles.read(os.path.join(SRC, 'gen7_tiles', f'{game}_{r}_{c}.ytd'))
                for r in range(3) for c in range(2)}
        recoloured, mapping = raster.match_colours(tris, base)
        changed = {k: v for k, v in mapping.items() if k != v}
        print(f'{game}: vector colours matched to the 2D tiles: {changed}')
        for (r, c), ras in base.items():
            day = raster.over(raster.draw_tile(recoloured, r, c, SIZE), raster.upscale(ras, SIZE))
            if fmt == 'DXT1':
                day[..., 3] = 255
            dark = to_night(day)
            tiles.write(day, fmt, f'{game}_{r}_{c}', os.path.join(args.out, f'{game}_{r}_{c}.ytd'))
            tiles.write(dark, fmt, f'{game}_{r}_{c}', os.path.join(args.out, f'{nite}_{r}_{c}.ytd'))
            if game == 'minimap_sea':
                keep_for_preview[(r, c)] = (day, dark)
            print(f'  {game}_{r}_{c} + {nite}_{r}_{c}  ({time.time() - t0:.0f}s)')

    # the radar's far overview: Gen7's own file by day, darkened at night
    lod = os.path.join(SRC, 'gen7_tiles', 'minimap_lod_128.ytd')
    shutil.copyfile(lod, os.path.join(args.out, 'minimap_lod_128.ytd'))
    tiles.write(to_night(tiles.read(lod)), 'DXT1', 'minimap_lod_128', os.path.join(args.out, f'{NIGHT_PREFIX}_lod_128.ytd'))
    print('  minimap_lod_128 + night')

    preview({k: v[0] for k, v in keep_for_preview.items()}, {k: v[1] for k, v in keep_for_preview.items()},
            args.previews, (24, 96, 168), tuple(int(v) for v in night(np.array([[24, 96, 168]], np.uint8))[0]))
    print(f'done in {time.time() - t0:.0f}s -> {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
