"""DIRTY ROOM: coarse eye briefs for a list of eye textures -> games/conker/face_briefs.json.

For each texture it keeps a handful of numbers, as a person would when writing a brief from a contact sheet:
sclera box, pupil centre and radius, iris colour and radius (positions to 1/32, colours to steps of 16).
The painting itself is done in the clean room by cleanroom.gfx.facepaint from those numbers.

    python -m games.conker.eyefit <rom> <id,id,...> [--merge]
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
    # pupil = dark pixels nearest their own median (ignores dark borders)
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
        b = fit(TL.decode_level(rom.flat[i].data, spec[str(i)]))
        if b and (str(i) not in briefs or "--force" in argv):
            briefs[str(i)] = b
            n += 1
    json.dump(briefs, open(OUT, "w"), indent=0)
    print(f"face briefs: {n} written, {len(briefs) - 1} total -> {OUT}")


if __name__ == "__main__":
    main(sys.argv)
