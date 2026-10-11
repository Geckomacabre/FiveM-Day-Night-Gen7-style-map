"""The night colour mapping for the Gen7 map tiles, as one function of colour.

Every tile holds land AND sea (the land tiles are opaque, sea included), so the
mapping has to tell them apart by colour alone:
  - neutral and green/tan colours (land, sand, city blocks, roads) have their
    lightness turned over, so dark roads come up light out of dark ground;
  - blue colours (sea, lakes, rivers, the shoreline gradient) keep their order
    but are pushed down dark, deep water darkest.
Then everything is tinted toward the slate the 3D minimap uses after dark
(vice_hud html/map3d.js NIGHT: land 42,42,62 / water 27,35,58 / road 90,86,100).
Alpha is left alone.
"""
import numpy as np

# --- sRGB <-> CIELAB (D65) ---------------------------------------------------
_M = np.array([[0.4124564, 0.3575761, 0.1804375],
               [0.2126729, 0.7151522, 0.0721750],
               [0.0193339, 0.1191920, 0.9503041]])
_MI = np.linalg.inv(_M)
_WHITE = np.array([0.95047, 1.0, 1.08883])


def _lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _gam(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def rgb_to_lab(rgb):
    xyz = _lin(rgb / 255.0) @ _M.T / _WHITE
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], -1)


def lab_to_rgb(lab):
    L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    fy = (L + 16) / 116
    f = np.stack([fy + a / 500, fy, fy - b / 200], -1)
    xyz = np.where(f > 6 / 29, f ** 3, 3 * (6 / 29) ** 2 * (f - 4 / 29)) * _WHITE
    return np.clip(np.round(_gam(xyz @ _MI.T) * 255.0), 0, 255).astype(np.uint8)


# --- the mapping -------------------------------------------------------------
# Lightness out for ground, turned over (darker in -> lighter out). The steep
# step between 20 and 29 keeps roads (L~19-20 in the day tiles) clearly above
# buildings (L~28-31), which would otherwise come out as light as the roads;
# sage land and the light-grey city lots (L~73-77) go down to ~19.
GROUND_L_IN = [0.0, 20.0, 24.0, 29.0, 74.0, 100.0]
GROUND_L_OUT = [56.0, 52.0, 44.0, 32.0, 19.0, 8.0]
# Lightness out for water, kept in order: deep sea L~40 -> 13, the near-white
# shoreline, rivers and rail lines (L~92) -> ~38, so they stay light lines on
# the dark ground the way they are on the day map.
WATER_L = (13.0, 0.48, 40.0)    # L' = a + b * (L - pivot)
# Tint: everything leans toward slate; a little of each colour's own hue is kept
# so sand, land and city still read as different things.
GROUND_AB = (3.0, -11.0, 0.30)  # a' = a0 + k*a, b' = b0 + k*b
WATER_AB = (2.0, -16.0, 0.15)


def water_weight(lab):
    """0 for ground, 1 for water. Water is anything blue (b* below zero), plus
    the near-white shoreline gradient, which is barely blue at all but lighter
    than anything on land (the lightest ground, sand, is L~78)."""
    L, b = lab[..., 0], lab[..., 2]
    blue = np.clip((-b - 4.0) / 12.0, 0.0, 1.0)     # b* -4 -> 0, -16 -> 1
    shore = np.clip((L - 83.0) / 5.0, 0.0, 1.0)     # L 83 -> 0, 88 -> 1
    return np.maximum(blue, shore)


def night(rgb):
    """rgb: (..., 3) uint8 -> (..., 3) uint8"""
    lab = rgb_to_lab(rgb.astype(np.float64))
    L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    w = water_weight(lab)

    gL = np.interp(L, GROUND_L_IN, GROUND_L_OUT)
    wL = WATER_L[0] + WATER_L[1] * (L - WATER_L[2])
    gA, gB = GROUND_AB[0] + GROUND_AB[2] * a, GROUND_AB[1] + GROUND_AB[2] * b
    # Sand (beaches, the desert: b* ~26) would come out a muddy dark brown;
    # the 3D minimap's night sand is a grey a little lighter than its land.
    sand = np.clip((b - 12.0) / 10.0, 0.0, 1.0)
    gL = gL + 7.0 * sand
    gA = gA - 1.5 * sand
    gB = gB - 4.0 * sand
    wA, wB = WATER_AB[0] + WATER_AB[2] * a, WATER_AB[1] + WATER_AB[2] * b

    out = np.stack([gL + (wL - gL) * w, gA + (wA - gA) * w, gB + (wB - gB) * w], -1)
    return lab_to_rgb(out)


if __name__ == '__main__':
    for c in [(24, 96, 168), (104, 152, 200), (224, 232, 232), (168, 184, 168),
              (208, 192, 144), (176, 184, 192), (48, 48, 48), (64, 64, 64), (160, 192, 216)]:
        n = night(np.array([c], dtype=np.uint8))[0]
        lab = rgb_to_lab(np.array([c], dtype=np.float64))[0]
        print(f'{c!s:18} L{lab[0]:5.1f} a{lab[1]:6.1f} b{lab[2]:6.1f}  w={water_weight(lab[None])[0]:.2f}  -> {tuple(int(x) for x in n)}')
