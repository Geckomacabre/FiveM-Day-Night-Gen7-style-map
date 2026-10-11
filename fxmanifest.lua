fx_version 'cerulean'
game 'gta5'
lua54 'yes'

name 'gen7_map'
author 'Alex106 (Remastered Gen7 Minimap v3.5) / FiveM day-night port'
description 'Remastered Gen7 map tiles for the big map and the radar, with a night version swapped in by the game clock'
version '1.0.0'

-- stream/ holds the map tiles. minimap_*.ytd replace the game's own; the
-- gen7night_*.ytd are the night versions, which client.lua swaps in over them.
-- Built by tools/build.py -- rebuild there rather than editing.

client_scripts {
    'config.lua',
    'client.lua',
}
