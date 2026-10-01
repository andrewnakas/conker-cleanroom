"""Dirty room: decide the layout of every flat texture and write the kept facts.

    python -m games.conker.texspec <rom> <usages.json> games/conker/spec/textures.json [--sheet dir]

Facts kept per texture (user scope): format, size, mip layout, 4x4 colour grid (16x16 from 128 px), 2-bit alpha.
Layout evidence: display-list tiles ("dl"), palette mode / loaded bytes from display lists plus image statistics
("ref"), or size class + image statistics ("guess").
"""
import collections
import json
import os
import sys

import numpy as np

from cleanroom.decomp import spec as cspec
from cleanroom.gfx import texfmt
from . import texlayout as TL
from .romtool import Rom

DIMS = [4, 8, 16, 32, 64, 128]
ODD_W = [24, 40, 44, 48, 56, 60, 80, 96]


def score(data, lay):
    try:
        img = TL.decode_level(data, lay).astype(np.float32)
    except Exception:
        return 9.0
    if img.shape[0] < 2 or img.shape[1] < 2:
        return 9.0
    l = img[..., :3].sum(-1) * (img[..., 3:4].sum(-1) > 0) + img[..., 3] * 0.5
    sd = float(l.std())
    if sd < 1e-3:
        return 0.5
    return float(np.abs(np.diff(l, axis=0)).mean() + np.abs(np.diff(l, axis=1)).mean()) / (2 * sd)


def candidates(P, fmt, siz, pal, exact=None):
    """All plain / mip layouts whose pixel bytes fit P (or equal `exact` loaded bytes)."""
    out = []
    for w in DIMS + ODD_W:
        s = TL.stride_for(w, siz)
        for tot in ([exact] if exact else [P, P - 8, P - 16]):
            if tot and tot > 0 and tot % s == 0 and 2 <= tot // s <= 256:
                out.append(dict(fmt=fmt, siz=siz, pal=pal, swap=True, levels=[[0, s, w, tot // s]]))
                break
        for h in DIMS:
            if w in DIMS and min(w, h) >= 4:
                lv, tot = TL.mip_levels(w, h, siz)
                if len(lv) > 1 and ((exact and tot == exact) or (not exact and P - 24 <= tot <= P)):
                    out.append(dict(fmt=fmt, siz=siz, pal=pal, swap=True, levels=lv))
    return out


def from_tiles(use, pal_modes, size):
    tiles = [t for t in use["tiles"] if t[0] != 7 and t[3] > 0]
    if not tiles:
        return None
    t0 = min(tiles, key=lambda t: t[4])
    fmt, siz = t0[1], t0[2]
    pal = 0
    if siz <= 1 and fmt in (0, 2):
        fmt = texfmt.CI
        pal = 32 if ("2" in pal_modes and siz == 0) else 512 if "1" in pal_modes else 32 if "2" in pal_modes else (32 if siz == 0 else 512)
    mul = 16 if siz == 3 else 8
    levels = []
    for t in sorted(tiles, key=lambda t: t[4]):
        if (t[1], t[2]) != (t0[1], t0[2]):
            continue
        w = t[5] or (1 << t[9])
        h = t[6] or (1 << t[10])
        if w < 1 or h < 1:
            return None
        stride = t[3] * mul
        if stride < TL.stride_for(w, siz):
            w = stride * 8 // TL.BPP[siz]
        off = t[4] * mul
        if off + stride * h > size - pal + 7:
            # clamp height to the payload (wrapped / partial loads)
            h = (size - pal - off) // stride
            if h < 1:
                continue
        levels.append([off, stride, w, h])
    if not levels:
        return None
    return dict(fmt=fmt, siz=siz, pal=pal, swap=True, levels=levels)


IMG_KINDS = {0x18: [(0, 3)], 0x10: [(0, 2)], 0x90: [(4, 1), (4, 0)], 0x70: [(3, 1), (3, 2), (3, 0)], 0x50: []}
TILE_VIEW = {1056: (2, 0, 32), 2560: (2, 1, 512)}
ALL_KINDS = [(2, 1, 512), (2, 0, 32), (0, 2, 0), (0, 3, 0), (3, 1, 0), (4, 1, 0), (4, 0, 0), (3, 2, 0), (3, 0, 0)]


VIEW_IDS = (4811, 7660)       # runtime ids of the tiled background views (decomp tiled-views manifest)


def decide(data, u, prior, idx=-1):
    size = len(data)
    pm = u["pal"]
    best = None
    for use in u["uses"]:
        lay = from_tiles(use, pm, size)
        if lay:
            n = len(lay["levels"]) * 1000 + use["n"]
            if best is None or n > best[0]:
                best = (n, lay)
    if best:
        return best[1], "dl"
    cands = []
    if u["uses"]:
        use = u["uses"][0]
        exact = use["texels"] * 2 if use["texels"] and use["texels"] > 0 else None
        if "2" in pm:
            kinds = [(2, 0, 32)]
        elif "1" in pm:
            kinds = [(2, 1, 512)]
        else:
            kinds = [(f, s, 0) for f, s in IMG_KINDS.get(use["img"], [])] or [k for k in ALL_KINDS if not k[2]]
        for f, s, p in kinds:
            cands += candidates(size - p, f, s, p, exact if exact and exact <= size - p else None)
        src = "ref"
    if not u["uses"] and size in TILE_VIEW and VIEW_IDS[0] <= idx <= VIEW_IDS[1]:
        # background view tiles: 64x32 storage proven by the tiled renderer (decomp docs/rzip-assets.md)
        f, s, p = TILE_VIEW[size]
        return dict(fmt=f, siz=s, pal=p, swap=True, levels=[[0, TL.stride_for(64, s), 64, 32]]), "view"
    if not cands:
        for f, s, p in ALL_KINDS:
            if size > p:
                cands += candidates(size - p, f, s, p)
        src = "guess" if not u["uses"] else "ref"
    if not cands:
        return dict(fmt=4, siz=1, pal=0, swap=True, levels=[[0, 8, 8, max(1, size // 8)]]), "raw"
    scored = []
    for c in cands:
        sc = score(data, c)
        key = (c["fmt"], c["siz"], c["pal"])
        if src == "guess":
            sc *= prior.get(key, 1.15)
        if len(c["levels"]) > 1:
            sc *= 0.97
        w, h = c["levels"][0][2:]
        sc *= 1 + 0.3 * max(0.0, abs(np.log2(w / h)) - 1)
        scored.append((sc, c))
    scored.sort(key=lambda t: t[0])
    return scored[0][1], src


_OV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "layout_overrides.json")
OVERRIDES = json.load(open(_OV)) if os.path.exists(_OV) else {}


def main(argv):
    r = Rom(argv[1])
    usages = json.load(open(argv[2]))
    out_path = argv[3]
    # pass 1: display-list proven kinds give a prior per size class
    prior_n = collections.defaultdict(collections.Counter)
    lays = {}
    for i, e in enumerate(r.flat):
        if e is None:
            continue
        u = usages[str(i)]
        if u["uses"] or u["pal"]:
            lay, src = decide(e.data, u, {}, i)
            lays[i] = (lay, src)
            prior_n[len(e.data)][(lay["fmt"], lay["siz"], lay["pal"])] += 1
    out = {}
    stat = collections.Counter()
    for i, e in enumerate(r.flat):
        if e is None:
            continue
        if str(i) in OVERRIDES:
            f, sz, p, w, h = OVERRIDES[str(i)]
            lay, src = dict(fmt=f, siz=sz, pal=p, swap=True, levels=[[0, TL.stride_for(w, sz), w, h]]), "fixed"
        elif i in lays:
            lay, src = lays[i]
        else:
            c = prior_n[len(e.data)]
            tot = sum(c.values())
            prior = {k: 1.0 - 0.3 * n / tot for k, n in c.items()} if tot else {}
            lay, src = decide(e.data, usages[str(i)], prior, i)
        img = TL.decode_level(e.data, lay)
        h, w = img.shape[:2]
        n = 16 if max(w, h) >= 128 else 4
        d = dict(size=len(e.data), src=src, **lay, grid=cspec.grid(img.astype(np.float32), n))
        if (img[..., 3] < 250).any():
            d["alpha2"] = cspec.alpha2(img[..., 3])
        out[i] = d
        stat[(src, texfmt.FMT_NAMES[lay["fmt"]] + str(TL.BPP[lay["siz"]]), "mip" if len(lay["levels"]) > 1 else "")] += 1
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(out, open(out_path, "w"), separators=(",", ":"))
    print(f"{len(out)} textures -> {out_path} ({os.path.getsize(out_path) // 1024} KB)")
    for k, n in sorted(stat.items(), key=lambda kv: -kv[1]):
        print(f"  {n:5d} {k[0]:5s} {k[1]} {k[2]}")
    if "--sheet" in argv:
        sheets(r, out, argv[argv.index("--sheet") + 1])


def sheets(r, spec, out_dir, per=160):
    """Dirty contact sheets (dev only): a sample per (source, size class)."""
    from PIL import Image
    os.makedirs(out_dir, exist_ok=True)
    groups = collections.defaultdict(list)
    for i, d in spec.items():
        groups[d["src"]].append(i)
    rng = np.random.default_rng(1)
    for src, ids in groups.items():
        ids = sorted(ids)
        pick = sorted(rng.choice(ids, min(per, len(ids)), replace=False).tolist())
        cell = 72
        cols = 16
        sheet = Image.new("RGB", (cols * cell, ((len(pick) + cols - 1) // cols) * cell), (40, 0, 40))
        for k, i in enumerate(pick):
            img = TL.decode_level(r.flat[i].data, spec[i])
            im = Image.fromarray(img, "RGBA")
            s = 64 / max(im.size)
            im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.NEAREST)
            bg = Image.new("RGB", im.size, (90, 90, 110))
            bg.paste(im, (0, 0), im)
            sheet.paste(bg, ((k % cols) * cell + 4, (k // cols) * cell + 4))
        sheet.save(os.path.join(out_dir, f"dirty_{src}.png"))
    print("sheets:", out_dir, {k: len(v) for k, v in groups.items()})


if __name__ == "__main__":
    main(sys.argv)
