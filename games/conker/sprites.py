"""Bank 00 sprite sets (plants, pickups...): n frames of [RGBA16 w x h, linear rows][I4 w x h plane, TMEM rows].

Dirty:  python -m games.conker.sprites spec <rom> <bank0_layout.json> games/conker/spec/sprites.json
        (layout = frame size per entry, found by image statistics in the dirty room)
Clean:  build(spec) -> {entry index: bytes}. Kept per frame: 4x4 colour grid, 1-bit alpha, 2-bit plane outline.
"""
import json
import os
import sys

import numpy as np

from cleanroom.decomp import gen as cgen
from cleanroom.decomp import spec as cspec
from cleanroom.gfx import texfmt
from . import texlayout as TL

BANK = 0


def spec(rom_path, layout_path, out):
    from .romtool import Rom
    ents = Rom(rom_path).banks[BANK][1]
    lay = json.load(open(layout_path))
    res = {}
    nf = 0
    for key, (w, h, n, _) in lay.items():
        d = ents[int(key)].data
        F = w * h * 2 + w * h // 2
        assert len(d) == n * F
        frames = []
        for k in range(n):
            o = k * F
            img = texfmt.decode(d[o:o + w * h * 2], w, h, texfmt.RGBA, texfmt.B16)
            plane = texfmt.decode(TL.unswap(d[o + w * h * 2:o + F], w // 2, h, 0).tobytes(), w, h, texfmt.I, texfmt.B4)[..., 0]
            frames.append(dict(grid=cspec.grid(img.astype(np.float32), 4), alpha2=cspec.alpha2(img[..., 3]),
                               plane2=cspec.alpha2(plane)))
            nf += 1
        res[key] = dict(w=w, h=h, frames=frames)
    json.dump(res, open(out, "w"), separators=(",", ":"))
    print(f"sprites: {len(res)} sets, {nf} frames -> {out}")


def build(spec_dir):
    S = json.load(open(os.path.join(spec_dir, "sprites.json")))
    out = {}
    for key, s in S.items():
        w, h = s["w"], s["h"]
        b = b""
        for k, f in enumerate(s["frames"]):
            rgba = cgen.upsample_grid(f["grid"], 4, w, h)
            rgba[..., :3] *= cgen.detail(cgen.h32("sprite", key, k), w, h, 0.05, 4.0)[..., None]
            cov = cgen.upsample_grid([[c[3]] * 4 for c in f["grid"]], 4, w, h)[..., 0] / 255.0
            rgba[..., :3] /= np.clip(cov, 0.25, 1.0)[..., None]
            rgba[..., 3] = cgen.unpack_alpha2(f["alpha2"], w, h)
            b += texfmt.encode(np.clip(rgba, 0, 255).astype(np.uint8), texfmt.RGBA, texfmt.B16)
            p = cgen.unpack_alpha2(f["plane2"], w, h)
            img = np.repeat(np.clip(p, 0, 255).astype(np.uint8)[..., None], 4, -1)
            b += TL.unswap(texfmt.encode(img, texfmt.I, texfmt.B4), w // 2, h, 0).tobytes()
        out[int(key)] = b
    return out


if __name__ == "__main__":
    spec(sys.argv[2], sys.argv[3], sys.argv[4])
