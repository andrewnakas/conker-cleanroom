"""Dev (dirty when the ROM is retail): lay flat tiles out in sequence to find their arrangement.

    python -m games.conker.mosaic <rom> <out.png> <ids> <cols[,r<rows>...]> [flip]   (r2 = column-major, 2 rows)
"""
import json
import sys

from PIL import Image

from . import texlayout as TL
from .romtool import Rom
from .sheet import SPEC, parse_ids


def main(argv):
    spec = json.load(open(SPEC))
    rom = Rom(argv[1])
    ids = [i for i in parse_ids(argv[3]) if str(i) in spec]
    flip = len(argv) > 5
    ims = []
    for i in ids:
        a = TL.decode_level(rom.flat[i].data, spec[str(i)])
        ims.append(Image.fromarray(a[::-1] if flip else a, "RGBA"))
    w, h = ims[0].size
    sheets = []
    for cols in argv[4].split(","):
        cm = cols.startswith("r")             # r<rows>: column-major (ids run down each column)
        cols = int(cols.lstrip("r"))
        if cm:
            rows, cols = cols, (len(ims) + cols - 1) // cols
        else:
            rows = (len(ims) + cols - 1) // cols
        s = Image.new("RGB", (cols * w, rows * h + 6), (95, 95, 120))
        for k, im in enumerate(ims):
            s.paste(im, ((k // rows) * w, (k % rows) * h) if cm else ((k % cols) * w, (k // cols) * h), im)
        sheets.append(s)
    out = Image.new("RGB", (max(s.width for s in sheets), sum(s.height for s in sheets)), (0, 50, 80))
    y = 0
    for s in sheets:
        out.paste(s, (0, y))
        y += s.height
    out.save(argv[2])
    print(argv[2], out.size, len(ims), "tiles", (w, h), sorted({im.size for im in ims}))


if __name__ == "__main__":
    main(sys.argv)
