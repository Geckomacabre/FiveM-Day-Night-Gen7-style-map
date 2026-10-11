--[[
    The Gen7 map by day, and its night version after dark.

    The day tiles are streamed under the game's own names (stream/minimap_*.ytd)
    and simply are the map. The night tiles (stream/gen7night_*.ytd) are drawn
    in their place with AddReplaceTexture.

    That swap is FiveM's, and it is tied to the texture the game has loaded at
    the moment it is made (extra-natives-five TextureReplacementNatives.cpp):
    when the game lets a map tile go and loads it again, the new copy is not
    swapped and the day tile shows -- the "it reverts after a while" people
    report with map swaps. The game does let them go: it holds each tile only
    while the big map or the radar needs it. So
    while the night map is up this resource holds every tile itself, day and
    night, and they never reload. By day it holds nothing.

    The open sea on the big map is not in the tiles; see Config.NightSeaTint.
]]

local RES = GetCurrentResourceName()
local KVP = 'gen7_map:mode'

-- HUD_COLOUR_PAUSEMAP_TINT and HUD_COLOUR_PAUSEMAP_TINT_HALF
-- (docs.fivem.net/docs/game-references/hud-colors)
local TINTS = { 157, 163 }

local TILES = {}
for row = 0, 2 do
    for col = 0, 1 do
        TILES[#TILES + 1] = { game = ('minimap_sea_%d_%d'):format(row, col), night = ('gen7night_sea_%d_%d'):format(row, col) }
        TILES[#TILES + 1] = { game = ('minimap_%d_%d'):format(row, col), night = ('gen7night_%d_%d'):format(row, col) }
    end
end
TILES[#TILES + 1] = { game = 'minimap_lod_128', night = 'gen7night_lod_128' }

local mode = GetResourceKvpString(KVP) or Config.Mode
local nightOn = false
local tintDay = {}

local function wantNight()
    if mode == 'night' then return true end
    if mode == 'day' then return false end
    local t = GetClockHours() + GetClockMinutes() / 60.0
    if Config.NightFrom > Config.NightTo then
        return t >= Config.NightFrom or t < Config.NightTo
    end
    return t >= Config.NightFrom and t < Config.NightTo
end

local function holdAll()
    for _, t in ipairs(TILES) do
        RequestStreamedTextureDict(t.game, false)
        RequestStreamedTextureDict(t.night, false)
    end
    local deadline = GetGameTimer() + 15000
    local missing
    repeat
        missing = nil
        for _, t in ipairs(TILES) do
            if not HasStreamedTextureDictLoaded(t.game) then missing = t.game break end
            if not HasStreamedTextureDictLoaded(t.night) then missing = t.night break end
        end
        if not missing then return true end
        Wait(50)
    until GetGameTimer() > deadline
    return false, missing
end

local function releaseAll()
    for _, t in ipairs(TILES) do
        SetStreamedTextureDictAsNoLongerNeeded(t.night)
        SetStreamedTextureDictAsNoLongerNeeded(t.game)
    end
end

local function swap()
    for _, t in ipairs(TILES) do
        AddReplaceTexture(t.game, t.game, t.night, t.game)
    end
end

local function setTint(night)
    if not Config.NightSeaTint then return end
    for _, index in ipairs(TINTS) do
        local day = tintDay[index]
        local rgb = night and Config.NightSeaTint or day
        -- keep the game's alpha: it is also how much the map itself is dimmed
        ReplaceHudColourWithRgba(index, rgb[1], rgb[2], rgb[3], day[4])
    end
end

local function toNight()
    local ok, missing = holdAll()
    if not ok then
        print(('^3[%s]^7 night map not applied: %s did not load'):format(RES, tostring(missing)))
        releaseAll()
        return false
    end
    swap()
    setTint(true)
    nightOn = true
    return true
end

local function toDay()
    -- undone while the tiles are still held, so the swap comes off the same
    -- textures it was put on; only then let them go
    for _, t in ipairs(TILES) do
        RemoveReplaceTexture(t.game, t.game)
    end
    releaseAll()
    setTint(false)
    nightOn = false
end

CreateThread(function()
    for _, index in ipairs(TINTS) do
        local r, g, b, a = GetHudColour(index)
        tintDay[index] = { r, g, b, a }
    end

    local failedAt = nil
    local pauseWas = false
    while true do
        local want = wantNight()
        if want and not nightOn then
            -- a failed load is tried again a minute later, not every second
            if not failedAt or GetGameTimer() - failedAt > 60000 then
                failedAt = not toNight() and GetGameTimer() or nil
            end
        elseif not want and nightOn then
            toDay()
        end

        -- The tiles are held, so the swap should never come off; putting it
        -- back each time the pause menu opens costs nothing and covers it if
        -- it ever does.
        local pause = IsPauseMenuActive()
        if nightOn and pause and not pauseWas then swap() end
        pauseWas = pause

        Wait(pause and 100 or 1000)
    end
end)

local function say(text)
    print(('[%s] %s'):format(RES, text))
    TriggerEvent('chat:addMessage', { args = { 'Map', text } })
end

RegisterCommand('mapmode', function(_, args)
    local m = (args[1] or ''):lower()
    if m ~= 'auto' and m ~= 'day' and m ~= 'night' then
        say(('map is %s (%s now). /mapmode auto | day | night'):format(mode, nightOn and 'night' or 'day'))
        return
    end
    mode = m
    SetResourceKvp(KVP, m)
    say(m == 'auto' and 'map follows the clock' or ('map stays on ' .. m))
end, false)

TriggerEvent('chat:addSuggestion', '/mapmode', 'The big map: day, night, or auto (follows the clock)', {
    { name = 'mode', help = 'auto | day | night' },
})

AddEventHandler('onResourceStop', function(name)
    if name ~= RES or not nightOn then return end
    for _, t in ipairs(TILES) do
        RemoveReplaceTexture(t.game, t.game)
    end
    setTint(false)
end)
