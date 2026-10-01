"""The small RLE system font (ROM 0x40F10, 95 glyphs): spec (dirty) and regeneration (clean).

Record: u8 width, u8 height, 2 metadata bytes, u32 record size, then (intensity nibble, run-1 nibble) bytes;
runs stop at the end of each scanline and at 16 pixels.

    python -m games.conker.fonts spec <rom> games/conker/spec/font.json     (dirty: metrics only)
    python -m games.conker.fonts sheet <out.png>                            (clean glyph sheet)
"""
import json
import os
import sys

import numpy as np

from cleanroom.gfx import strokefont as S

START, END, COUNT = 0x40F10, 0x42450, 95
MAP_OFF = 0x80085930 - 0x80082B20        # glyph index -> Latin-1 character, in game data

EXTRA = {
    "$": [[(4, 1), (3, 0.5), (1, 0.5), (0, 1.5), (0, 2.5), (4, 3.5), (4, 4.5), (3, 5.5), (1, 5.5), (0, 5)], [(2, -0.3), (2, 6.3)]],
    ";": [[(2, 1.5), (2, 2.2)], [(2, 4.5), (2, 5.2), (1.2, 6.3)]],
    "[": [[(3, 0), (1, 0), (1, 6), (3, 6)]],
    "]": [[(1, 0), (3, 0), (3, 6), (1, 6)]],
    "{": [[(3, 0), (2, 0.5), (2, 2.5), (1, 3), (2, 3.5), (2, 5.5), (3, 6)]],
    "}": [[(1, 0), (2, 0.5), (2, 2.5), (3, 3), (2, 3.5), (2, 5.5), (1, 6)]],
    "^": [[(0, 5), (2, 1), (4, 5)]],
    "~": [[(0, 3.5), (1, 2.5), (3, 3.5), (4, 2.5)]],
    "@": [[(3, 4), (3, 2), (1.5, 2), (1.5, 4), (4, 4), (4, 1), (3, 0), (1, 0), (0, 1), (0, 5), (1, 6), (4, 6)]],
}
RING = [[(1, 0), (3, 0), (4, 1), (4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0)]]
ACCENT = {"uml": [[(1, 0), (1.3, 0)], [(2.7, 0), (3, 0)]], "grave": [[(1, 0), (2.4, 1)]], "acute": [[(3, 0), (1.6, 1)]],
          "circ": [[(0.8, 1), (2, 0), (3.2, 1)]]}
DECOMP = {"Ä": "Auml", "Ö": "Ouml", "Ü": "Uuml", "À": "Agrave", "Â": "Acirc", "É": "Eacute", "È": "Egrave", "Ë": "Euml",
          "Ê": "Ecirc", "Î": "Icirc", "Ï": "Iuml", "Ô": "Ocirc", "Û": "Ucirc", "Ù": "Ugrave", "Ú": "Uacute"}
SYMBOL = {58: "R", 94: "C"}             # ® and © (ring + letter); the map's ']' and '@' slots


def _lines(mask, lines, th=1.1):
    h, w = mask.shape
    sx, sy = (w - 1 - th) / 4.0, (h - 1 - th) / 6.0
    return S._stroke(mask, lines, 0.5 + th / 2, 0.5 + th / 2, sx, sy, th)


def _fit(ch, w, h):
    """Stroke-font character, ink cropped and fitted to the w x h cell."""
    if ch in EXTRA:
        return _lines(np.zeros((h, w), np.float32), EXTRA[ch])
    for H in range(max(h, 10), 3, -1):
        m = S.render(ch, w, H, thickness=1.15)
        rows = np.nonzero(m.max(1) > 0.2)[0]
        if not len(rows):
            return np.zeros((h, w), np.float32)
        m = m[rows[0]:rows[-1] + 1]
        if m.shape[0] <= h:
            out = np.zeros((h, w), np.float32)
            top = (h - m.shape[0]) // 2
            out[top:top + m.shape[0]] = m
            return out
    return np.zeros((h, w), np.float32)


def draw(index, ch, w, h):
    """(h, w) coverage 0..1 for glyph `index` mapped to Latin-1 character `ch`."""
    if index in SYMBOL:
        m = _lines(np.zeros((h, w), np.float32), RING, 1.0)
        inner = _fit(SYMBOL[index], max(3, w - 4), max(4, h - 4))
        m[2:2 + inner.shape[0], 2:2 + inner.shape[1]] = np.maximum(m[2:2 + inner.shape[0], 2:2 + inner.shape[1]], inner)
        return m
    if ch == "ß":
        return _fit("B", w, h)
    up = ch.upper()
    if up == "0":
        return _lines(np.zeros((h, w), np.float32), RING, 1.15)
    if up == "ß":
        return _fit("B", w, h)
    if up == "Ç":
        m = np.zeros((h, w), np.float32)
        m[:h - 2] = _fit("C", w, h - 2)
        m[h - 2:, w // 2] = 1.0
        return m
    if up in DECOMP:
        base, acc = DECOMP[up][0], DECOMP[up][1:]
        m = np.zeros((h, w), np.float32)
        m[3:] = _fit(base, w, h - 3)
        a = np.zeros((2, w), np.float32)
        th = 0.9
        S._stroke(a, ACCENT[acc], 0.5 + (w - 5) / 2.0, 0.5, 1.0, 1.0, th)
        m[:2] = a
        return m
    return _fit(up, w, h)


def spec(rom_path, out):
    from .romtool import Rom
    r = Rom(rom_path)
    rom = r.rom
    o = START
    glyphs = []
    for _ in range(COUNT):
        w, h = rom[o], rom[o + 1]
        glyphs.append([w, h, rom[o + 2:o + 4].hex()])
        o += int.from_bytes(rom[o + 4:o + 8], "big")
    chars = bytes(r.gdata[MAP_OFF:MAP_OFF + COUNT]).decode("latin-1")
    json.dump(dict(glyphs=glyphs, chars=chars, used=o - START), open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"font: {len(glyphs)} glyph metrics -> {out}")


def rle(w, h, px):
    out = bytearray()
    o = 0
    n = w * h
    while o < n:
        run = 1
        while run < 16 and o + run < n and (o + run) % w and px[o + run] == px[o]:
            run += 1
        out.append(px[o] | (run - 1))
        o += run
    return bytes(out)


def build(spec_dir):
    """Clean font table bytes (fixed size END - START). The records fill exactly the retail span (`used`):
    the game walks the table to its end, so a shorter table leaves it reading zero-size records (black boot).
    Runs are split (legal, one extra byte each) until the size matches."""
    d = json.load(open(os.path.join(spec_dir, "font.json"), encoding="utf-8"))
    encs = []
    for i, (w, h, meta) in enumerate(d["glyphs"]):
        m = draw(i, d["chars"][i], w, h)
        px = (np.clip(np.round(m * 15), 0, 15).astype(np.uint8) << 4).ravel().tobytes()
        encs.append(bytearray(rle(w, h, px)))
    deficit = d["used"] - sum(8 + len(e) for e in encs)
    assert deficit >= 0, f"font table {-deficit} bytes too large"
    k = 0
    while deficit:
        e = encs[k % len(encs)]
        j = next((j for j in range(len(e)) if e[j] & 0x0F), None)
        if j is not None:
            v, run = e[j] & 0xF0, (e[j] & 0x0F) + 1
            e[j:j + 1] = bytes((v | (run - 2), v))
            deficit -= 1
        k += 1
    out = b""
    for (w, h, meta), e in zip(d["glyphs"], encs):
        out += bytes((w, h)) + bytes.fromhex(meta) + (8 + len(e)).to_bytes(4, "big") + bytes(e)
    assert len(out) == d["used"]
    return out + bytes(END - START - len(out))


def sheet(spec_dir, out):
    from PIL import Image
    d = json.load(open(os.path.join(spec_dir, "font.json"), encoding="utf-8"))
    s = Image.new("L", (16 * 30, 6 * 30), 40)
    for i, (w, h, _) in enumerate(d["glyphs"]):
        m = (np.clip(draw(i, d["chars"][i], w, h), 0, 1) * 255).astype(np.uint8)
        s.paste(Image.fromarray(m).resize((w * 2, h * 2), Image.NEAREST), ((i % 16) * 30 + 2, (i // 16) * 30 + 2))
    s.save(out)
    print(out)


if __name__ == "__main__":
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spec")
    if sys.argv[1] == "spec":
        spec(sys.argv[2], sys.argv[3])
    else:
        sheet(here, sys.argv[2])
