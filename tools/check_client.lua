-- Runs gen7_map's real config.lua + client.lua under a
-- small strict mock of FiveM (virtual clock, texture dictionaries that take a
-- few frames to load, the swap and HUD-colour natives) and checks:
--   day by day, night by night, at the configured hours, both directions
--   while night: every tile, day and night, is held (so none can reload)
--   by day: nothing held, no swap, the sea tint is the game's again
--   /mapmode day|night|auto, kept in KVP; a bad argument changes nothing
--   the swap is put back when the pause menu opens
--   a tile that never loads: no swap, nothing left held, retried later
--   resource stop at night undoes the swap and the tint
-- usage: lua check_client.lua [path to gen7_map, default ..]

local dir = arg[1] or '..'
local fails, checks = 0, 0
local function check(ok, what)
    checks = checks + 1
    if not ok then fails = fails + 1; print('FAIL ' .. what) end
end

local function newWorld()
    local W = {
        now = 0, hours = 12, minutes = 0, pause = false,
        held = {}, loadsAt = {}, never = {}, swaps = {}, hud = {}, kvp = {},
        threads = {}, commands = {}, handlers = {}, chat = {}, printed = {},
    }
    W.hud[157] = { 0, 0, 0, 215 }
    W.hud[163] = { 0, 0, 0, 215 }
    return W
end

local W
local function env()
    local G = {}
    setmetatable(G, { __index = function(_, k)
        if _G[k] ~= nil and (k == 'ipairs' or k == 'pairs' or k == 'tostring' or k == 'string' or k == 'math'
            or k == 'table' or k == 'type' or k == 'next' or k == 'select' or k == 'error' or k == 'pcall') then
            return _G[k]
        end
        error('unknown global ' .. tostring(k), 2)
    end, __newindex = rawset })
    G.print = function(s) W.printed[#W.printed + 1] = s end
    G.GetCurrentResourceName = function() return 'gen7_map' end
    G.GetGameTimer = function() return W.now end
    G.Wait = function(ms) coroutine.yield(ms) end
    G.CreateThread = function(fn) W.threads[#W.threads + 1] = { co = coroutine.create(fn), at = W.now } end
    G.GetClockHours = function() return W.hours end
    G.GetClockMinutes = function() return W.minutes end
    G.IsPauseMenuActive = function() return W.pause end
    G.GetResourceKvpString = function(k) return W.kvp[k] end
    G.SetResourceKvp = function(k, v) assert(type(v) == 'string'); W.kvp[k] = v end
    G.RequestStreamedTextureDict = function(name, p)
        assert(type(name) == 'string' and p == false)
        if not W.held[name] then W.held[name] = true; W.loadsAt[name] = W.now + 120 end
    end
    G.HasStreamedTextureDictLoaded = function(name)
        return W.held[name] == true and not W.never[name] and W.now >= W.loadsAt[name]
    end
    G.SetStreamedTextureDictAsNoLongerNeeded = function(name) W.held[name] = nil end
    G.AddReplaceTexture = function(a, b, c, d)
        assert(G.HasStreamedTextureDictLoaded(a) and G.HasStreamedTextureDictLoaded(c), 'swap before load: ' .. a)
        assert(a == b and d == a, 'texture names should be the game tile name')
        W.swaps[a] = c
    end
    G.RemoveReplaceTexture = function(a, b)
        assert(a == b)
        assert(W.held[a], 'swap removed after the tile was let go: ' .. a)
        W.swaps[a] = nil
    end
    G.GetHudColour = function(i) local c = W.hud[i]; return c[1], c[2], c[3], c[4] end
    G.ReplaceHudColourWithRgba = function(i, r, g, b, a)
        for _, v in ipairs({ r, g, b, a }) do assert(math.type(v) == 'integer', 'hud colour must be ints') end
        W.hud[i] = { r, g, b, a }
    end
    G.RegisterCommand = function(name, fn) W.commands[name] = fn end
    G.TriggerEvent = function(name, data) if name == 'chat:addMessage' then W.chat[#W.chat + 1] = data.args[2] end end
    G.AddEventHandler = function(name, fn) W.handlers[name] = fn end
    return G
end

local function boot(kvp)
    W = newWorld()
    for k, v in pairs(kvp or {}) do W.kvp[k] = v end
    local G = env()
    for _, f in ipairs({ 'config.lua', 'client.lua' }) do
        local chunk = assert(loadfile(dir .. '/' .. f, 't', G))
        chunk()
    end
    return G
end

local function run(ms)
    local stop = W.now + ms
    while W.now < stop do
        W.now = W.now + 10
        for _, t in ipairs(W.threads) do
            if coroutine.status(t.co) ~= 'dead' and W.now >= t.at then
                local ok, wait = coroutine.resume(t.co)
                assert(ok, wait)
                t.at = W.now + (wait or 0)
            end
        end
    end
end

local TILE_COUNT = 13
local function count(t) local n = 0; for _ in pairs(t) do n = n + 1 end; return n end
local function isNight() return count(W.swaps) == TILE_COUNT end
local function isDay() return count(W.swaps) == 0 end

-- day and night by the clock ----------------------------------------------------
local G = boot()
run(3000)
check(isDay(), 'noon: day map')
check(count(W.held) == 0, 'noon: nothing held')
check(W.hud[157][1] == 0 and W.hud[157][4] == 215, 'noon: tint untouched')

W.hours, W.minutes = 20, 10
run(3000)
check(isDay(), '20:10: still day (night from 20:15)')
W.minutes = 20
run(3000)
check(isNight(), '20:20: night map')
check(count(W.held) == 2 * TILE_COUNT, '20:20: all 26 dictionaries held, got ' .. count(W.held))
check(W.swaps.minimap_sea_0_0 == 'gen7night_sea_0_0' and W.swaps.minimap_1_1 == 'gen7night_1_1'
    and W.swaps.minimap_lod_128 == 'gen7night_lod_128', 'night: the right night tile for each game tile')
check(W.hud[157][1] == 12 and W.hud[157][3] == 52 and W.hud[157][4] == 215, 'night: sea tint navy, alpha kept')
check(W.hud[163][3] == 52, 'night: half tint too')

W.hours, W.minutes = 3, 0
run(3000)
check(isNight(), '03:00: night')
W.hours, W.minutes = 5, 50
run(3000)
check(isDay(), '05:50: day again')
check(count(W.held) == 0, '05:50: everything let go')
check(W.hud[157][1] == 0 and W.hud[157][3] == 0 and W.hud[157][4] == 215, 'day: tint restored')

-- the pause menu puts the swap back ---------------------------------------------
W.hours = 23
run(3000)
W.swaps.minimap_sea_1_0 = nil            -- as if it had come off somehow
W.pause = true
run(1200)                                -- the loop looks once a second outside the menu
check(W.swaps.minimap_sea_1_0 == 'gen7night_sea_1_0', 'pause menu opening puts the swap back')
W.pause = false
run(1000)

-- /mapmode --------------------------------------------------------------------------
W.commands.mapmode(0, { 'day' })
run(2000)
check(isDay() and W.kvp['gen7_map:mode'] == 'day', '/mapmode day at 23:00: day map, saved')
W.commands.mapmode(0, { 'sideways' })
run(2000)
check(isDay() and W.kvp['gen7_map:mode'] == 'day', 'bad /mapmode changes nothing')
check(W.chat[#W.chat]:find('auto | day | night', 1, true) ~= nil, 'bad /mapmode says how to use it')
W.hours = 12
W.commands.mapmode(0, { 'NIGHT' })
run(2000)
check(isNight(), '/mapmode night at noon: night map')
W.commands.mapmode(0, { 'auto' })
run(2000)
check(isDay(), '/mapmode auto at noon: day map')

-- the saved choice beats the config on the next start ------------------------------
boot({ ['gen7_map:mode'] = 'night' })
W.hours = 12
run(3000)
check(isNight(), 'saved /mapmode night is used on the next start')

-- a tile that never loads ---------------------------------------------------------
boot()
W.never.gen7night_sea_2_1 = true
W.hours = 22
run(20000)
check(isDay(), 'a tile that never loads: no swap at all')
check(count(W.held) == 0, 'a tile that never loads: nothing left held')
local printedOnce = #W.printed
run(30000)
check(#W.printed == printedOnce, 'not retried every second')
W.never.gen7night_sea_2_1 = nil
run(45000)
check(isNight(), 'retried a minute later and works once it loads')

-- resource stop at night -------------------------------------------------------------
W.handlers.onResourceStop('gen7_map')
check(isDay(), 'resource stop undoes the swap')
check(W.hud[157][3] == 0, 'resource stop restores the tint')

print(('%d checks, %d failed'):format(checks, fails))
os.exit(fails == 0 and 0 or 1)
