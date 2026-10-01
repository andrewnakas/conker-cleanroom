"""DIRTY ROOM: coarse eye briefs for a list of eye textures -> games/conker/face_briefs.json.

For each texture it keeps a handful of numbers, as a person would when writing a brief from a contact sheet:
sclera box, pupil centre and radius, iris colour and radius (positions to 1/32, colours to steps of 16).
The painting itself is done in the clean room by cleanroom.gfx.facepaint from those numbers.

    python -m games.conker.eyefit <rom> <id,id,...> [--force] [--ellipse]

Two fits: default = coarse map of the white area + pupils (lidded and two-eye textures); --ellipse = one
centred round eye. Which one suits a texture is chosen by eye from the A/B sheet.
"""
import json
import os
import sys

import numpy as np

from . import texlayout as TL
from .romtool import Rom
from .sheet import parse_ids

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "face_briefs.json")
q = lambda v: round(float(v) * 32) / 32
qc = lambda c: [int(min(255, round(float(v) / 16) * 16)) for v in c]


def fit(img):
    """Brief: coarse map of the white of the eye (8 cells across the short side, 2 bits each), then up to three
    pupils (centre, radius, optional iris colour and radius)."""
    from scipy import ndimage
    h, w = img.shape[:2]
    a = img[..., 3] > 128
    rgb = img[..., :3].astype(np.float32)
    mx, mn = rgb.max(-1), rgb.min(-1)
    white = (mn > 170) & a
    dark = (mx < 70) & a
    if white.sum() < 8 or dark.sum() < 2:
        return None
    # pupils: dark blobs touching / inside the white area
    near_white = ndimage.binary_dilation(ndimage.binary_fill_holes(white | dark) & ndimage.binary_dilation(white, iterations=2), iterations=1)
    lab, n = ndimage.label(dark & near_white)
    if not n:
        return None
    sizes = np.asarray(ndimage.sum(np.ones_like(lab), lab, range(1, n + 1)))
    # shading in the corners is dark too: prefer compact blobs that do not touch the texture border
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    good = []
    for k in range(1, n + 1):
        ys, xs = np.nonzero(lab == k)
        fill = len(xs) / ((xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1))
        if k not in edge and fill >= 0.5:
            good.append(k)
    cand = good or list(range(1, n + 1))
    top = max(sizes[k - 1] for k in cand)
    keep = [k for k in sorted(cand, key=lambda k: -sizes[k - 1])[:2] if sizes[k - 1] >= max(2, 0.5 * top)]
    sat = (mx - mn) > 50
    yy, xx = np.mgrid[0:h, 0:w]
    pupils = []
    iris_mask = np.zeros((h, w), bool)
    for k in keep:
        ys, xs = np.nonzero(lab == k)
        px, py, rp = xs.mean() + 0.5, ys.mean() + 0.5, np.sqrt(len(xs) / np.pi)
        dist = np.hypot(xx + 0.5 - px, yy + 0.5 - py)
        ring = (dist < rp * 2.6) & a & ~white & ~dark & sat
        p = {"p": [q(px / w), q(py / h)], "r": round(float(rp / w), 3)}
        if ring.sum() > 0.25 * max(1, ((dist < rp * 2.6) & (dist >= rp)).sum()):
            p["iris"] = qc(np.median(rgb[ring], axis=0))
            p["ri"] = round(float(np.sqrt((len(xs) + ring.sum()) / np.pi) / w), 3)
            iris_mask |= ring
        pupils.append(p)
    # coarse coverage of the eye area (white + pupil + iris)
    area = white | iris_mask | (np.isin(lab, keep))
    area = ndimage.binary_fill_holes(area)
    gx, gy = (8, max(4, round(8 * h / w))) if w <= h else (max(4, round(8 * w / h)), 8)
    cells = ""
    for j in range(gy):
        for i in range(gx):
            c = area[j * h // gy:(j + 1) * h // gy, i * w // gx:(i + 1) * w // gx].mean()
            cells += str(int(round(c * 3)))
    sc = np.median(rgb[white], axis=0)
    ops = [{"cells": [gx, gy, cells], "c": qc(sc) if sc.min() < 235 else [250, 250, 250], "clip": True}]
    asp = w / h
    for p in pupils:
        x, y = p["p"]
        if "iris" in p:
            ops.append({"e": [x, y, p["ri"], p["ri"] * asp], "c": p["iris"]})
        ops.append({"e": [x, y, p["r"], p["r"] * asp], "c": [12, 12, 18]})
        ops.append({"hl": [x - p["r"] * 0.35, y - p["r"] * asp * 0.35, max(p["r"] * 0.3, 0.6 / w)]})
    ops.append({"clip": None})
    return {"base": "grid", "ops": ops}


def fit_ellipse(img):
    """Simple centred eye: sclera = bounding ellipse of the white area, one pupil, optional iris."""
    h, w = img.shape[:2]
    a = img[..., 3] > 128
    rgb = img[..., :3].astype(np.float32)
    mx, mn = rgb.max(-1), rgb.min(-1)
    white = (mn > 170) & a
    dark = (mx < 70) & a
    if white.sum() < 8 or dark.sum() < 2:
        return None
    ys, xs = np.nonzero(white | dark)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    cx, cy, rx, ry = (x0 + x1) / 2 / w, (y0 + y1) / 2 / h, (x1 - x0) / 2 / w, (y1 - y0) / 2 / h
    dy, dx = np.nonzero(dark)
    px, py = np.median(dx), np.median(dy)
    near = (np.abs(dx - px) < w * 0.3) & (np.abs(dy - py) < h * 0.3)
    px, py = dx[near].mean() + 0.5, dy[near].mean() + 0.5
    rp = np.sqrt(near.sum() / np.pi)
    yy, xx = np.mgrid[0:h, 0:w]
    dist = np.hypot(xx + 0.5 - px, yy + 0.5 - py)
    ring = (dist < rp * 2.4) & a & ~white & ~dark
    sat = (mx - mn) > 50
    iris = None
    ri = rp
    if (ring & sat).sum() > 0.25 * max(1, ((dist < rp * 2.4) & (dist > rp)).sum()):
        iris = qc(np.median(rgb[ring & sat], axis=0))
        ri = np.sqrt((near.sum() + (ring & sat).sum()) / np.pi)
    e = {"c": [q(cx), q(cy)], "r": [q(max(rx, 2 / w)), q(max(ry, 2 / h))],
         "look": [round(float((px / w - cx) / max(rx, 1e-3)), 2), round(float((py / h - cy) / max(ry, 1e-3)), 2)],
         "irisr": round(float(ri / w / max(rx, 1e-3)), 2), "irisy": round(float((rx * w) / max(ry * h, 1e-3)), 2),
         "iris": iris or [16, 16, 24], "pupil": round(float(rp / ri), 2) if iris else 0}
    sc = np.median(rgb[white], axis=0)
    if sc.min() < 235:
        e["sclera"] = qc(sc)
    return {"base": "grid", "ops": [{"eye": e}]}


def main(argv):
    rom = Rom(argv[1])
    spec = json.load(open(os.path.join(HERE, "spec", "textures.json")))
    briefs = json.load(open(OUT)) if os.path.exists(OUT) else {"_doc": "Eye / face briefs (cleanroom.gfx.facepaint), in payload row order."}
    n = 0
    for i in parse_ids(argv[2]):
        b = (fit_ellipse if "--ellipse" in argv else fit)(TL.decode_level(rom.flat[i].data, spec[str(i)]))
        if b is None and "--force" in argv:
            briefs.pop(str(i), None)
        if b and (str(i) not in briefs or "--force" in argv):
            briefs[str(i)] = b
            n += 1
    json.dump(briefs, open(OUT, "w"), indent=0)
    print(f"face briefs: {n} written, {len(briefs) - 1} total -> {OUT}")


if __name__ == "__main__":
    main(sys.argv)
