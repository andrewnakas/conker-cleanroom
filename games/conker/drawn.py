"""Clean room: textures we draw ourselves instead of grid-regenerating (text first).

`text_briefs.json`: { "<flat id>": {"t": "LINE|LINE", "fg": [r,g,b], "bg": [r,g,b] | null, "flip": bool,
                                   "font": "lilita|luckiest|rubik|press", "cut": bool, "stroke": [r,g,b] | null,
                                   "span": [ids...]  (one text across several tiles, left to right)} }
The words are the text as it appears in the game (kept fact); the lettering is ours (OFL fonts in ./fonts).
bg null keeps the regenerated colour grid behind the text. flip = payload rows stored bottom-up.
"""
import json
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from cleanroom.gfx import texfmt

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = {"lilita": "LilitaOne-Regular.ttf", "luckiest": "LuckiestGuy-Regular.ttf", "rubik": "Rubik.ttf",
         "press": "PressStart2P-Regular.ttf", "round": "MPLUSRounded1c-ExtraBold.ttf"}
SS = 4


def _font(name, size):
    f = ImageFont.truetype(os.path.join(HERE, "fonts", FONTS[name]), size)
    if name == "rubik":                       # variable font: use the bold instance
        try:
            f.set_variation_by_axes([700])
        except Exception:
            pass
    return f


def text_mask(lines, w, h, font="lilita", fill=0.92, stroke=0):
    """(h, w) coverage 0..1 (and stroke coverage) of centred lines fitted to the box."""
    W, H = w * SS, h * SS
    size = H
    while size > 6:
        f = _font(font, size)
        boxes = [f.getbbox(l, stroke_width=stroke * SS) for l in lines]
        tw = max(b[2] - b[0] for b in boxes)
        lh = max(b[3] - b[1] for b in boxes)
        gap = int(lh * 0.12)
        if tw <= W * fill and lh * len(lines) + gap * (len(lines) - 1) <= H * fill:
            break
        size -= max(1, size // 24)
    ink = Image.new("L", (W, H), 0)
    edge = Image.new("L", (W, H), 0)
    total = lh * len(lines) + gap * (len(lines) - 1)
    y = (H - total) // 2
    for l, b in zip(lines, boxes):
        x = (W - (b[2] - b[0])) // 2 - b[0]
        if stroke:
            ImageDraw.Draw(edge).text((x, y - b[1]), l, font=f, fill=255, stroke_width=stroke * SS, stroke_fill=255)
        ImageDraw.Draw(ink).text((x, y - b[1]), l, font=f, fill=255)
        y += lh + gap
    r = lambda im: np.asarray(im.resize((w, h), Image.LANCZOS), np.float32) / 255.0
    return r(ink), r(edge)


def draw_text(base, d, brief, part=None):
    """base: level-0 RGBA float from the grid (storage orientation). Returns RGBA float."""
    h, w = base.shape[:2]
    lines = brief["t"].split("|")
    stroke = 1 if brief.get("stroke") else 0
    if part:                                  # one text over several tiles
        k, n = part
        ink, edge = text_mask(lines, w * n, h, brief.get("font", "lilita"), brief.get("fill", 0.92), stroke)
        ink, edge = ink[:, k * w:(k + 1) * w], edge[:, k * w:(k + 1) * w]
    else:
        ink, edge = text_mask(lines, w, h, brief.get("font", "lilita"), brief.get("fill", 0.92), stroke)
    if brief.get("flip", True):
        ink, edge = ink[::-1], edge[::-1]
    fg = np.array(brief.get("fg", [255, 255, 255]), np.float32)
    out = base.copy()
    if d["fmt"] == texfmt.I:
        v = ink * 255
        out[..., :3] = v[..., None]
        out[..., 3] = v
        return out
    if brief.get("bg") is not None:
        out[..., :3] = np.array(brief["bg"], np.float32)
        out[..., 3] = 255
    # a kept alpha outline would show the retail lettering behind ours: text on a cut-out is always redrawn
    if brief.get("cut") or ("alpha2" in d and brief.get("bg") is None and not brief.get("keep_alpha")):
        cov = np.maximum(ink, edge)
        out[..., :3] = fg
        if stroke:
            out[..., :3] = np.array(brief["stroke"], np.float32) * (1 - ink[..., None]) + fg * ink[..., None]
        out[..., 3] = cov * 255
        return out
    if stroke:
        s = np.array(brief["stroke"], np.float32)
        out[..., :3] = out[..., :3] * (1 - edge[..., None]) + s * edge[..., None]
    out[..., :3] = out[..., :3] * (1 - ink[..., None]) + fg * ink[..., None]
    return out


def hooks():
    from . import generate
    out = {}
    p = os.path.join(HERE, "text_briefs.json")
    briefs = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    for key, b in briefs.items():
        if key.startswith("_"):
            continue
        ids = b.get("span") or [int(key)]
        for k, i in enumerate(ids):
            part = (k, len(ids)) if len(ids) > 1 else None
            out[i] = (lambda i, d, b=b, part=part: draw_text(generate.base_image(i, d), d, b, part))
    return out
