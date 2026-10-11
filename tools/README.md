# tools: building the tiles

Builds this resource's map tiles (`../stream`) from the Remastered Gen7
Minimap mod: day tiles at 3072 with the mod's vector detail drawn in, and a
night version of each.

```bash
python build.py          # ~4 min: writes ../stream + out/ previews
python check_bc.py       # DXT1/DXT5 encoder round trip through CodeWalker
lua check_client.lua       # client logic on a mock (26 checks)
python mutate.py         # breaks the client 16 ways; all must be caught
```

`out/bigmap_day_night.jpg` and `out/downtown_day_night.jpg` show the result.

## Inputs (`source/`, not in git)

The mod's own files, from Alex106's download
(https://www.gta5-mods.com/misc/nxg-radar, v3.5: the `Legacy.oiv` package,
which is a zip; extract it with 7-Zip):
- `source/gen7_tiles/` — `content/update/x64/data/cdimages/scaleform_generic/*.ytd`
- `source/gen7_vectors/` — the 65 `.ydd` inside `content/update/x64/levels/gta5/minimap.rpf`
  (`ytdtool rpfls "<GTA folder>" minimap.rpf source/gen7_vectors`)

## How the map tiles fit together

- 2D tiles: a 2 x 3 grid of 4500 m squares from world (-4140, 8400), row 0
  in the north. The big map draws `minimap_sea_<row>_<col>` (open sea left
  transparent), the radar draws `minimap_<row>_<col>` (opaque), plus
  `minimap_lod_128` for the radar's far view. The game loads and drops them
  as it needs them, which is why `gen7_map` holds them while its night swap
  is on.
- Vector tiles `minimap_<col>_<row>.ydd`: drawables `supertile_back_*` (ground),
  `supertile_sea_*` (not drawn on the big map), `supertile_fore_*_tile_*`
  (roads, buildings), all flat vertex colours in world coordinates, layered
  by z. Normally the big map shows the 2D tiles zoomed out and the vectors
  zoomed in; with empty vector tiles streamed (ls_map_lite does this) the 2D
  tiles are what you see.
- The vectors' colours are not the 2D tiles' (sand is light blue in the
  vectors, for one), so `raster.match_colours` recolours each vector colour
  to what the 2D tiles show there.
- Open sea on the big map is the HUD colour `HUD_COLOUR_PAUSEMAP_TINT` (157)
  showing under the tiles; its alpha also dims the map, so only the colour is
  changed at night.

## Files

- `build.py` — the build
- `raster.py` — vector triangles into tile pixels, colour matching, compositing
- `vectors.py` — reads `ytdtool yddmesh` output
- `nightcolor.py` — the night colour mapping (roads up, ground down, water kept
  in order and darkened, all tinted to vice_hud's night slate)
- `bc.py` — DXT1/DXT5 encoder/decoder in numpy (nothing here compresses DDS)
- `tiles.py` — reads/writes `.ytd` through `ytdtool`
- `ytdtool/` — CodeWalker.Core helper: `info`, `dump`, `fromdds`, `pack`, `rpfls`, `yddmesh`, `yddinfo`
