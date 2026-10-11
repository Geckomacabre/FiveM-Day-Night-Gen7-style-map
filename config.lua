Config = {}

-- 'auto' follows the game clock; 'day' or 'night' keeps one map all the time.
-- Each player can override this for themselves with /mapmode (kept between
-- sessions).
Config.Mode = 'auto'

-- When the night map is up, in game hours. vice_hud's drawn 3D minimap fades
-- into its night look between 19:30 and 21:00 and back out between 05:00 and
-- 06:30 (Config.Map3D.nightHours there); the big map cannot fade, so it changes
-- over halfway through each of those.
Config.NightFrom = 20.25    -- 20:15
Config.NightTo   = 5.75     -- 05:45

-- The open sea on the big map, beyond the coast's shading, is not part of the
-- tiles: the game draws the colour HUD_COLOUR_PAUSEMAP_TINT behind them (only
-- faintly, its alpha also dims the map). At night its colour is set to this,
-- so the open water leans navy too; by day it goes back to what it was.
-- false leaves it alone.
Config.NightSeaTint = { 12, 24, 52 }
