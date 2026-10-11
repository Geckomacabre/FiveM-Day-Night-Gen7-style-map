"""Round trip: decode a real tile, compress it with bc.py, pack it with
ytdtool, decode the new file with CodeWalker, and compare. Proves the block
layout matches what the game's own decoder expects, not just bc.py's.
usage: python check_bc.py"""
import os
import sys
import tempfile

import numpy as np

import bc
import tiles

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'source', 'gen7_tiles')


def psnr(a, b):
    mse = np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2)
    return float('inf') if mse == 0 else 10 * np.log10(255 ** 2 / mse)


def main():
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        for name, fmt in (('minimap_1_0', 'DXT1'), ('minimap_sea_1_0', 'DXT5')):
            src = os.path.join(SRC, name + '.ytd')
            orig = tiles.read(src)
            out = tiles.write(orig, fmt, name, os.path.join(tmp, name + '.ytd'))
            back = tiles.read(out)
            h, w = orig.shape[:2]
            ours = (bc.decode_dxt1(bc.encode_dxt1(orig[..., :3]), h, w) if fmt == 'DXT1'
                    else bc.decode_dxt5(bc.encode_dxt5(orig), h, w))
            ch = 3 if fmt == 'DXT1' else 4
            p_cw = psnr(orig[..., :ch], back[..., :ch])
            # CodeWalker and bc.py decode the same bytes; they may round the
            # in-between palette entries differently by one step at most
            diff = np.abs(back[..., :ch].astype(int) - ours[..., :ch].astype(int)).max()
            good = p_cw > 38 and diff <= 2
            ok &= good
            print(f'{"ok  " if good else "FAIL"} {name} ({fmt}): re-encoded vs original {p_cw:.1f} dB, '
                  f'CodeWalker vs bc.py decode max diff {diff}')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
