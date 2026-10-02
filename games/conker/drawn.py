"""Clean room: textures we draw ourselves instead of grid-regenerating (text first).

`text_briefs.json`: { "<flat id>": {"t": "LINE|LINE", "fg": [r,g,b], "bg": [r,g,b] | null, "flip": bool,
                                   "font": "lilita|luckiest|rubik|press", "cut": bool, "stroke": [r,g,b] | null,
                                   "span": [ids...]  (one text across several tiles, left to right),
                                   "box": [x0,y0,x1,y1] (fractions of the upright picture)} }
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
    k, n = part or (0, 1)                     # one text over several tiles
    W = w * n
    x0, y0, x1, y1 = brief.get("box", [0, 0, 1, 1])     # coarse placement (fractions of the upright picture)
    x0, x1, y0, y1 = int(x0 * W), int(x1 * W), int(y0 * h), int(y1 * h)
    ink, edge = np.zeros((h, W), np.float32), np.zeros((h, W), np.float32)
    ink[y0:y1, x0:x1], edge[y0:y1, x0:x1] = text_mask(lines, x1 - x0, y1 - y0, brief.get("font", "lilita"),
                                                      brief.get("fill", 0.92), stroke)
    ink, edge = ink[:, k * w:(k + 1) * w], edge[:, k * w:(k + 1) * w]
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
    for sc in briefs.get("_screens", []):     # one picture over a grid of tiles
        for k, i in enumerate(sc["ids"]):
            out[i] = (lambda i, d, sc=sc, k=k: screen_tile(d, sc, k))
    p = os.path.join(HERE, "face_briefs.json")
    faces = json.load(open(p)) if os.path.exists(p) else {}
    for key, b in faces.items():
        if not key.startswith("_"):
            out[int(key)] = (lambda i, d, b=b: face(i, d, b))
    if os.environ.get("CONKER_IDS"):          # dev: print the flat id on every not yet identified tile
        spec = json.load(open(os.path.join(HERE, "spec", "textures.json")))
        want = os.environ["CONKER_IDS"]
        from .sheet import parse_ids
        ids = [int(k) for k, d in spec.items() if d["src"] == "guess"] if want == "guess" else parse_ids(want)
        for i in ids:
            if i not in out and str(i) in spec and spec[str(i)]["fmt"] in (texfmt.RGBA, texfmt.CI, texfmt.IA):
                out[i] = id_tile
    return out


def id_tile(i, d):
    """Dev tile: the id in two rows on a hue that depends on it (storage order = reads upright when not flipped)."""
    _, _, w, h = d["levels"][0]
    s = str(i)
    ink, _ = text_mask([s[:-2], s[-2:]] if w <= h * 1.5 else [s], w, h, "press", 0.9)
    import colorsys
    bg = np.array(colorsys.hsv_to_rgb((i * 0.381) % 1.0, 0.75, 0.55), np.float32) * 255
    out = np.zeros((h, w, 4), np.float32)
    out[..., :3] = bg * (1 - ink[..., None]) + 255 * ink[..., None]
    out[..., 3] = 255
    out[0, :, :3] = 255                       # white line marks the first stored row
    return out


_SCREENS = {}


def screen(sc):
    """Whole picture (H, W, 4) of a tiled screen: text items in coarse boxes (fractions of the picture)."""
    key = sc["ids"][0]
    if key in _SCREENS:
        return _SCREENS[key]
    tw, th = sc["tile"]
    rows = sc["rows"]
    cols = len(sc["ids"]) // rows
    W, H = cols * tw, rows * th
    out = np.zeros((H, W, 4), np.float32)
    out[..., :3] = np.array(sc.get("bg", [0, 0, 0]), np.float32)
    cover = np.zeros((H, W), np.float32)
    for it in sc["items"]:
        x0, y0, x1, y1 = it["box"]
        x0, x1, y0, y1 = int(x0 * W), int(x1 * W), int(y0 * H), int(y1 * H)
        ink, edge = text_mask(it["t"].split("|"), x1 - x0, y1 - y0, it.get("font", "luckiest"), 0.98, 1 if it.get("stroke") else 0)
        reg = out[y0:y1, x0:x1, :3]
        if it.get("stroke"):
            reg[:] = reg * (1 - edge[..., None]) + np.array(it["stroke"], np.float32) * edge[..., None]
        reg[:] = reg * (1 - ink[..., None]) + np.array(it["fg"], np.float32) * ink[..., None]
        cover[y0:y1, x0:x1] = np.maximum(cover[y0:y1, x0:x1], np.maximum(ink, edge))
    out[..., 3] = cover * 255
    _SCREENS[key] = out
    return out


def screen_tile(d, sc, k):
    tw, th = sc["tile"]
    rows = sc["rows"]
    c, r = (k // rows, k % rows) if sc.get("order", "col") == "col" else (k % (len(sc["ids"]) // rows), k // (len(sc["ids"]) // rows))
    t = screen(sc)[r * th:(r + 1) * th, c * tw:(c + 1) * tw].copy()
    if "alpha2" not in d or not sc.get("cut"):
        t[..., 3] = 255
    return t[::-1] if sc.get("flip") else t


def face(i, d, brief):
    """Eye / face painted from a brief over the regenerated grid (payload row order)."""
    from cleanroom.decomp import gen as cgen
    from cleanroom.gfx import facepaint
    _, _, w, h = d["levels"][0]
    alpha = cgen.unpack_alpha2(d["alpha2"], w, h) if "alpha2" in d else None
    grid = d["grid"]
    if brief.get("flip"):                     # painted upside down (lid on the far rows), then flipped back
        n = int(round(len(grid) ** 0.5))
        grid = [c for row in reversed([grid[k * n:(k + 1) * n] for k in range(n)]) for c in row]
        alpha = alpha[::-1] if alpha is not None else None
    out = facepaint.render(brief, w, h, grid=grid, alpha=alpha, seed=cgen.h32("face", i))
    return out[::-1] if brief.get("flip") else out
