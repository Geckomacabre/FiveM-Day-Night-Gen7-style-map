"""Breaks gen7_map's client in ways that matter and checks check_client.lua
notices each one. usage: python mutate.py"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.normpath(os.path.join(HERE, '..'))

MUTATIONS = [
    ('client.lua', "        RequestStreamedTextureDict(t.game, false)\n", '', 'day tiles not held at night'),
    ('client.lua', "        RequestStreamedTextureDict(t.night, false)\n", '', 'night tiles never requested'),
    ('client.lua', "AddReplaceTexture(t.game, t.game, t.night, t.game)", "AddReplaceTexture(t.game, t.game, t.night, t.night)", 'wrong texture name'),
    ('client.lua', "    releaseAll()\n    setTint(false)\n    nightOn = false", "    setTint(false)\n    nightOn = false", 'never lets go by day'),
    ('client.lua', "    for _, t in ipairs(TILES) do\n        RemoveReplaceTexture(t.game, t.game)\n    end\n    releaseAll()",
     "    releaseAll()\n    for _, t in ipairs(TILES) do\n        RemoveReplaceTexture(t.game, t.game)\n    end", 'lets go before undoing the swap'),
    ('client.lua', "ReplaceHudColourWithRgba(index, rgb[1], rgb[2], rgb[3], day[4])", "ReplaceHudColourWithRgba(index, rgb[1], rgb[2], rgb[3], 255)", 'tint alpha changed'),
    ('client.lua', "local rgb = night and Config.NightSeaTint or day", "local rgb = Config.NightSeaTint", 'tint never restored'),
    ('client.lua', "return t >= Config.NightFrom or t < Config.NightTo", "return t >= Config.NightFrom and t < Config.NightTo", 'night across midnight broken'),
    ('client.lua', "TILES[#TILES + 1] = { game = 'minimap_lod_128', night = 'gen7night_lod_128' }\n", '', 'overview tile left out'),
    ('client.lua', "        if nightOn and pause and not pauseWas then swap() end\n", '', 'pause menu does not re-apply'),
    ('client.lua', "    SetResourceKvp(KVP, m)\n", '', '/mapmode not saved'),
    ('client.lua', "    if m ~= 'auto' and m ~= 'day' and m ~= 'night' then", "    if m == '' then", 'bad /mapmode accepted'),
    ('client.lua', "        releaseAll()\n        return false", "        return false", 'failed load keeps tiles held'),
    ('client.lua', "if not failedAt or GetGameTimer() - failedAt > 60000 then", "if true then", 'failed load retried every second'),
    ('client.lua', "    if name ~= RES or not nightOn then return end", "    do return end", 'resource stop leaves the swap'),
    ('config.lua', "Config.NightFrom = 20.25", "Config.NightFrom = 21.0", 'night hours moved'),
]


def main():
    survived = []
    for path, old, new, what in MUTATIONS:
        with tempfile.TemporaryDirectory() as tmp:
            dst = os.path.join(tmp, 'gen7_map')
            shutil.copytree(RES, dst, ignore=shutil.ignore_patterns('stream'))
            with open(os.path.join(dst, path), encoding='utf-8') as f:
                src = f.read()
            if old not in src:
                print(f'?? {what}: pattern not found')
                survived.append(what)
                continue
            with open(os.path.join(dst, path), 'w', encoding='utf-8') as f:
                f.write(src.replace(old, new, 1))
            r = subprocess.run(['lua', os.path.join(HERE, 'check_client.lua'), dst], capture_output=True, text=True)
            caught = r.returncode != 0
            print(f'{"caught  " if caught else "SURVIVED"} {what}')
            if not caught:
                survived.append(what)
    print(f'{len(MUTATIONS) - len(survived)}/{len(MUTATIONS)} caught')
    return 1 if survived else 0


if __name__ == '__main__':
    sys.exit(main())
