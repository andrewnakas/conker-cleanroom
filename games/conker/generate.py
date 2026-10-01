"""Clean room: build the clean ROM from the retail container (code + kept facts) and games/conker/spec.

    python -m games.conker.generate <retail rom> <out clean rom> [--only textures,...]

Every flat texture payload is regenerated from its spec (grid + alpha outline + own palette); hooks in
`drawn.py` (text, faces, HUD) override single textures.
"""
import json
import os
import sys

import numpy as np
from PIL import Image

from cleanroom.decomp import gen as cgen
from cleanroom.gfx import texfmt
from . import texlayout as TL
from .romtool import Rom

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "spec")


def base_image(i, d):
    """Level-0 RGBA (float) from the kept facts."""
    _, _, w, h = d["levels"][0]
    n = int(round(len(d["grid"]) ** 0.5))
    rgba = cgen.upsample_grid(d["grid"], n, w, h)
    rgba[..., :3] *= cgen.detail(cgen.h32("conker", i), w, h, 0.05, 4.0)[..., None]
    if "alpha2" in d:
        a = cgen.unpack_alpha2(d["alpha2"], w, h)
        if d["fmt"] == texfmt.I:
            rgba[..., :3] = a[..., None]
        elif a.max() > 0:
            # grid cells average over transparent texels too: undo the darkening inside the outline
            cov = cgen.upsample_grid([[c[3]] * 4 for c in d["grid"]], n, w, h)[..., 0] / 255.0
            rgba[..., :3] /= np.clip(cov, 0.25, 1.0)[..., None]
        rgba[..., 3] = a
    else:
        rgba[..., 3] = 255
    return np.clip(rgba, 0, 255)


def shrink(img, w, h):
    H, W = img.shape[:2]
    fy, fx = max(1, H // h), max(1, W // w)
    return img[:h * fy, :w * fx].reshape(h, fy, w, fx, 4).mean((1, 3))


GRAIN = float(os.environ.get("CONKER_GRAIN", 1.5))
CI8_COLOURS = 64     # fewer distinct indices keep the flat stream inside its fixed ROM span


def quantise(levels, ncol, seed, limit=256):
    """Own palette for all levels. Returns (index images, palette bytes RGBA5551)."""
    px = np.concatenate([l.reshape(-1, 4) for l in levels])
    opaque = px[:, 3] >= 128
    has_clear = bool((~opaque).any())
    n = min(ncol, limit) - (1 if has_clear else 0)
    rgb = np.clip(px[:, :3], 0, 255).astype(np.uint8)
    src = rgb[opaque] if opaque.any() else rgb[:1]
    im = Image.fromarray(src.reshape(1, -1, 3), "RGB").quantize(colors=min(n, 256), method=Image.MEDIANCUT, dither=Image.NONE)
    pal = np.array(im.getpalette()[:n * 3], np.int32).reshape(-1, 3)
    used = len(set(np.asarray(im).ravel().tolist()))
    pal = pal[:max(1, used)]
    order = np.random.default_rng(seed).permutation(len(pal))
    pal = pal[order]
    # nearest palette entry per pixel
    d2 = ((rgb[:, None, :].astype(np.int32) - pal[None, :, :]) ** 2).sum(-1) if len(rgb) * len(pal) < 4_000_000 else None
    if d2 is None:
        idx = np.concatenate([((rgb[k:k + 4096, None, :].astype(np.int32) - pal[None]) ** 2).sum(-1).argmin(1)
                              for k in range(0, len(rgb), 4096)])
    else:
        idx = d2.argmin(1)
    table = np.zeros((ncol, 4), np.uint8)
    table[:len(pal), :3] = pal
    table[:len(pal), 3] = 255
    if has_clear:
        clear = len(pal)
        table[clear] = (0, 0, 0, 0)
        idx = np.where(opaque, idx, clear)
    pal_bytes = texfmt.encode(table[None], texfmt.RGBA, texfmt.B16)
    out, o = [], 0
    for l in levels:
        hh, ww = l.shape[:2]
        out.append(idx[o:o + hh * ww].reshape(hh, ww).astype(np.uint8))
        o += hh * ww
    return out, pal_bytes


def build_texture(i, d, level0=None):
    """Payload bytes for flat id i. level0: optional drawn RGBA override (h, w, 4)."""
    lay = d
    img = np.asarray(level0, np.float32) if level0 is not None else base_image(i, d)
    levels = [img] + [shrink(img, w, h) for _, _, w, h in d["levels"][1:]]
    # seeded grain: breaks up flat runs (banding, and chance byte runs shared with any other image)
    rng = np.random.default_rng(cgen.h32("grain", i))
    levels = [np.concatenate([l[..., :3] + rng.uniform(-GRAIN, GRAIN, l.shape[:2] + (1,)),
                              l[..., 3:]], -1) for l in levels]
    out = bytearray(d["size"])
    if d["fmt"] == texfmt.CI:
        idx, palb = quantise(levels, d["pal"] // 2, cgen.h32("pal", i), CI8_COLOURS)
        out[len(out) - d["pal"]:] = palb
        levels = idx
    else:
        levels = [np.clip(l, 0, 255).astype(np.uint8) for l in levels]
    for k, (off, stride, w, h) in enumerate(d["levels"]):
        b = TL.encode_level(levels[k], lay, k)
        end = min(len(out) - d["pal"], off + len(b))
        out[off:end] = b[:end - off]
    return bytes(out)


def textures(rom, hooks=None):
    spec = json.load(open(os.path.join(SPEC, "textures.json")))
    n = drawn = 0
    for key, d in spec.items():
        i = int(key)
        img = hooks.get(i)(i, d) if hooks and i in hooks else None
        drawn += img is not None
        rom.set_flat(i, build_texture(i, d, img))
        n += 1
    print(f"textures: {n} regenerated ({drawn} drawn)")


def main(argv):
    rom = Rom(argv[1])
    only = argv[argv.index("--only") + 1].split(",") if "--only" in argv else None
    if not only or "textures" in only:
        try:
            from . import drawn
            hooks = drawn.hooks()
        except ImportError:
            hooks = None
        textures(rom, hooks)
    if not only or "font" in only:
        from . import fonts
        rom.fonts = fonts.build(SPEC)
        print("font: 95 glyphs redrawn")
    if not only or "sprites" in only:
        from . import sprites
        for i, b in sprites.build(SPEC).items():
            rom.set_bank(sprites.BANK, i, b)
        print("sprites: bank 00 regenerated")
    if (not only or "audio" in only) and os.path.exists(os.path.join(SPEC, "samples.json")):
        from . import audio
        ents = rom.banks[audio.BANK][1]
        ext, tbl = audio.build(ents[1].data, SPEC, cache=os.environ.get("CONKER_AUDIO_CACHE", "D:/n64work/conker/work/audio_cache.pkl"))
        rom.set_bank(audio.BANK, 1, ext)
        rom.set_bank(audio.BANK, 2, tbl)
        print("audio: wave table resynthesised")
    data = rom.build()
    open(argv[2], "wb").write(data)
    import hashlib
    print(f"flat stream {rom.flat_used[0]}/{rom.flat_used[1]} bytes")
    print(f"clean rom -> {argv[2]} sha1 {hashlib.sha1(data).hexdigest()[:12]}")


if __name__ == "__main__":
    main(sys.argv)
