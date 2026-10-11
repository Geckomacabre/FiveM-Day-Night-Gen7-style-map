"""Block compression (DXT1 / DXT5) and decompression in numpy, for map tiles.

Nothing on this machine compresses DDS (no texconv, and Pillow here cannot
write BC formats), so this is a straightforward encoder: per 4x4 block the
colour endpoints are the ends of the block's principal axis, rounded to 5:6:5,
and each pixel takes the nearest of the four palette colours. Map tiles are
large flat areas with soft edges between two colours, which is the case this
does well. Alpha (DXT5) takes the block's min and max with the eight-step ramp.

Layouts (little-endian, blocks in row-major order):
  DXT1  u16 c0, u16 c1, u32 indices (2 bits/pixel)            8 bytes/block
  DXT5  u8 a0, u8 a1, 48-bit alpha indices (3 bits/pixel), then a DXT1-style
        colour block (always four colours)                    16 bytes/block
"""
import numpy as np


def _to_blocks(img):
    h, w, c = img.shape
    if h % 4 or w % 4:
        raise ValueError('image size must be a multiple of 4')
    return img.reshape(h // 4, 4, w // 4, 4, c).transpose(0, 2, 1, 3, 4).reshape(-1, 16, c)


def _from_blocks(blocks, h, w):
    c = blocks.shape[-1]
    return blocks.reshape(h // 4, w // 4, 4, 4, c).transpose(0, 2, 1, 3, 4).reshape(h, w, c)


def _pack565(c):
    c = np.clip(np.rint(c), 0, 255)
    r = np.rint(c[..., 0] * 31 / 255).astype(np.uint16)
    g = np.rint(c[..., 1] * 63 / 255).astype(np.uint16)
    b = np.rint(c[..., 2] * 31 / 255).astype(np.uint16)
    return (r << 11) | (g << 5) | b


def _unpack565(v):
    v = v.astype(np.uint32)
    r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
    return np.stack([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)], -1).astype(np.float32)


def _colour_block(rgb):
    """rgb: (B,16,3) float32 -> structured (B,) of c0,c1,indices, four-colour mode"""
    m = rgb.mean(1, keepdims=True)
    x = rgb - m
    cov = np.einsum('bni,bnj->bij', x, x)
    v = np.ones((len(rgb), 3), np.float32) / np.sqrt(3.0)
    for _ in range(8):
        v = np.einsum('bij,bj->bi', cov, v)
        n = np.linalg.norm(v, axis=1, keepdims=True)
        v = np.where(n > 1e-6, v / np.maximum(n, 1e-6), np.float32(1 / np.sqrt(3.0)))
    t = np.einsum('bni,bi->bn', x, v)
    hi = m[:, 0] + t.max(1)[:, None] * v
    lo = m[:, 0] + t.min(1)[:, None] * v
    c0, c1 = _pack565(hi), _pack565(lo)

    # four-colour mode needs c0 > c1; equal endpoints mean a flat block (index 0)
    swap = c0 < c1
    c0, c1 = np.where(swap, c1, c0), np.where(swap, c0, c1)
    p0, p1 = _unpack565(c0), _unpack565(c1)
    pal = np.stack([p0, p1, (2 * p0 + p1) / 3, (p0 + 2 * p1) / 3], 1)      # (B,4,3)
    d = ((rgb[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1)          # (B,16,4)
    idx = d.argmin(-1).astype(np.uint32)
    idx[c0 == c1] = 0
    bits = (idx << (2 * np.arange(16, dtype=np.uint32))).sum(1, dtype=np.uint64).astype(np.uint32)

    out = np.zeros(len(rgb), dtype=[('c0', '<u2'), ('c1', '<u2'), ('i', '<u4')])
    out['c0'], out['c1'], out['i'] = c0, c1, bits
    return out


def encode_dxt1(rgb):
    """(H,W,3) uint8 -> bytes (opaque DXT1)"""
    return _colour_block(_to_blocks(rgb.astype(np.float32))).tobytes()


def encode_dxt5(rgba):
    """(H,W,4) uint8 -> bytes"""
    blocks = _to_blocks(rgba.astype(np.float32))
    col = _colour_block(blocks[..., :3])

    a = blocks[..., 3]
    a0, a1 = a.max(1), a.min(1)
    # code 0 = a0, 1 = a1, 2..7 = the six steps from a0 towards a1
    step = np.array([0, 7, 1, 2, 3, 4, 5, 6], np.float32) / 7
    pal = a0[:, None] * (1 - step) + a1[:, None] * step                  # (B,8)
    idx = np.abs(a[:, :, None] - pal[:, None, :]).argmin(-1).astype(np.uint64)
    idx[a0 == a1] = 0
    bits = (idx << (3 * np.arange(16, dtype=np.uint64))).sum(1, dtype=np.uint64)

    out = np.zeros(len(blocks), dtype=[('a0', 'u1'), ('a1', 'u1'), ('ai', 'u1', (6,)),
                                       ('c0', '<u2'), ('c1', '<u2'), ('i', '<u4')])
    out['a0'], out['a1'] = a0.astype(np.uint8), a1.astype(np.uint8)
    out['ai'] = ((bits[:, None] >> (8 * np.arange(6, dtype=np.uint64))) & 0xFF).astype(np.uint8)
    out['c0'], out['c1'], out['i'] = col['c0'], col['c1'], col['i']
    return out.tobytes()


def _decode_colour(c0, c1, bits):
    p0, p1 = _unpack565(c0), _unpack565(c1)
    pal = np.stack([p0, p1, (2 * p0 + p1) / 3, (p0 + 2 * p1) / 3], 1)
    idx = (bits[:, None] >> (2 * np.arange(16, dtype=np.uint32))) & 3
    return np.take_along_axis(pal, idx[..., None].astype(np.int64).repeat(3, -1), 1)


def decode_dxt1(data, h, w):
    """bytes -> (H,W,3) uint8 (four-colour blocks only, which is all encode_dxt1 writes)"""
    b = np.frombuffer(data, dtype=[('c0', '<u2'), ('c1', '<u2'), ('i', '<u4')])
    rgb = _decode_colour(b['c0'], b['c1'], b['i'])
    return np.clip(np.rint(_from_blocks(rgb, h, w)), 0, 255).astype(np.uint8)


def decode_dxt5(data, h, w):
    b = np.frombuffer(data, dtype=[('a0', 'u1'), ('a1', 'u1'), ('ai', 'u1', (6,)),
                                   ('c0', '<u2'), ('c1', '<u2'), ('i', '<u4')])
    rgb = _decode_colour(b['c0'], b['c1'], b['i'])
    a0, a1 = b['a0'].astype(np.float32), b['a1'].astype(np.float32)
    bits = (b['ai'].astype(np.uint64) << (8 * np.arange(6, dtype=np.uint64))).sum(1, dtype=np.uint64)
    idx = ((bits[:, None] >> (3 * np.arange(16, dtype=np.uint64))) & 7).astype(np.int64)
    step = np.array([0, 7, 1, 2, 3, 4, 5, 6], np.float32) / 7
    pal = a0[:, None] * (1 - step) + a1[:, None] * step
    # a0 <= a1 is the six-step mode with 0 and 255 at the end; encode_dxt5 only
    # writes it for flat blocks (a0 == a1, every index 0), where both agree
    a = np.take_along_axis(pal, idx, 1)
    rgba = np.concatenate([rgb, a[..., None]], -1)
    return np.clip(np.rint(_from_blocks(rgba, h, w)), 0, 255).astype(np.uint8)
