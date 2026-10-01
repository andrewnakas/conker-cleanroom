"""Contact sheets of flat textures with their ids (dirty when the ROM is retail, clean otherwise).

    python -m games.conker.sheet <rom> <out.png> text [N] [skip]     top-N by text score (non-view textures)
    python -m games.conker.sheet <rom> <out.png> ids 100-180,2000    explicit ids / ranges
    python -m games.conker.sheet <rom> <out.png> src guess [N] [skip]
    python -m games.conker.sheet - <out.png> clean [ids]             clean generation (all briefed ids by default)

Images are shown upright (payload rows are stored bottom-up).
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

from cleanroom import find_text
from . import texlayout as TL
from .romtool import Rom

SPEC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spec", "textures.json")


def upright(rom, spec, i):
    return TL.decode_level(rom.flat[i].data, spec[str(i)])[::-1]


def parse_ids(s):
    out = []
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += range(int(a), int(b) + 1)
        else:
            out.append(int(part))
    return out


def main(argv):
    spec = json.load(open(SPEC))
    mode = argv[3]
    if mode == "clean":                       # no ROM: generate the listed ids (briefs applied) and show them
        from . import generate, drawn
        hooks = drawn.hooks()
        ids = [i for i in (parse_ids(argv[4]) if len(argv) > 4 else sorted(hooks)) if str(i) in spec]

        class _E:
            def __init__(self, data):
                self.data = data

        class _R:
            flat = {}
        rom = _R()
        for i in ids:
            d = spec[str(i)]
            rom.flat[i] = _E(generate.build_texture(i, d, hooks[i](i, d) if i in hooks else None))
        mode = "ids"
        argv = argv[:4] + [",".join(map(str, ids))]
    else:
        rom = Rom(argv[1])
    if mode == "ids":
        ids = [i for i in parse_ids(argv[4]) if str(i) in spec]
    else:
        n = int(argv[5 if mode == "src" else 4]) if len(argv) > (5 if mode == "src" else 4) else 200
        skip = int(argv[6 if mode == "src" else 5]) if len(argv) > (6 if mode == "src" else 5) else 0
        if mode == "src":
            ids = [int(k) for k, d in spec.items() if d["src"] == argv[4]][skip:skip + n]
        else:
            sc = [(find_text.text_score(upright(rom, spec, int(k))), int(k)) for k, d in spec.items() if d["src"] != "view"]
            sc.sort(reverse=True)
            ids = sorted(i for _, i in sc[skip:skip + n])
    cell, scale, cols = 76, 1, 18
    items = []
    for i in ids:
        im = Image.fromarray(upright(rom, spec, i), "RGBA")
        s = 64 / max(im.size)
        if s > 1:
            im = im.resize((int(im.width * s), int(im.height * s)), Image.NEAREST)
        items.append((i, im))
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 4)), (0, 50, 80))
    d = ImageDraw.Draw(sheet)
    for k, (i, im) in enumerate(items):
        x, y = (k % cols) * cell, (k // cols) * (cell + 4)
        bg = Image.new("RGB", im.size, (95, 95, 120))
        bg.paste(im, (0, 0), im)
        sheet.paste(bg, (x + 2, y + 12))
        d.text((x + 2, y), str(i), fill=(255, 255, 0))
    sheet.save(argv[2])
    print(argv[2], len(items), "textures")


if __name__ == "__main__":
    main(sys.argv)
