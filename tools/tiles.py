"""Reading and writing map tiles through ytdtool (CodeWalker.Core)."""
import json
import os
import struct
import subprocess
import tempfile

import numpy as np

import bc

HERE = os.path.dirname(os.path.abspath(__file__))
YTDTOOL = os.path.join(HERE, 'ytdtool', 'bin', 'Release', 'net8.0', 'ytdtool.exe')


def _run(*args):
    r = subprocess.run([YTDTOOL, *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f'ytdtool {args[0]} failed: {r.stderr.strip() or r.stdout.strip()}')
    return r.stdout


def info(ytd):
    """[{name, width, height, format, levels, stride, dataLength}]"""
    return json.loads(_run('info', ytd))


def read(ytd, texture=None):
    """The top mip, decoded by CodeWalker, as (H,W,4) uint8 RGBA."""
    t = info(ytd)[0] if texture is None else next(x for x in info(ytd) if x['name'] == texture)
    with tempfile.TemporaryDirectory() as tmp:
        raw = os.path.join(tmp, 'px.bgra')
        _run('dump', ytd, t['name'], raw)
        bgra = np.fromfile(raw, np.uint8).reshape(t['height'], t['width'], 4)
    return bgra[..., [2, 1, 0, 3]].copy()


def dds(rgba, fmt):
    """A single-mip DXT1/DXT5 .dds file of `rgba` (H,W,4) uint8."""
    h, w = rgba.shape[:2]
    data = bc.encode_dxt1(rgba[..., :3]) if fmt == 'DXT1' else bc.encode_dxt5(rgba)
    # DDSD_CAPS|HEIGHT|WIDTH|PIXELFORMAT|MIPMAPCOUNT|LINEARSIZE; DDPF_FOURCC; DDSCAPS_TEXTURE
    header = (b'DDS ' + struct.pack('<7I', 124, 0x000A1007, h, w, len(data), 0, 1) + bytes(44) +
              struct.pack('<2I4s5I', 32, 0x4, fmt.encode(), 0, 0, 0, 0, 0) +
              struct.pack('<5I', 0x1000, 0, 0, 0, 0))
    return header + data


def write(rgba, fmt, texture, out):
    """A new .ytd at `out` holding one texture called `texture`: `rgba`
    compressed as `fmt` ('DXT1' opaque, 'DXT5' with alpha), one mip level, as
    the game's own map tiles are."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'tile.dds')
        with open(path, 'wb') as f:
            f.write(dds(rgba, fmt))
        _run('fromdds', path, texture, out)
    return out
