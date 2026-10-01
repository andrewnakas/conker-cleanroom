"""DIRTY-ROOM CHECK: clean ROM vs retail ROM over every regenerated stream.

    python -m games.conker.taint <retail rom> <clean rom> [--pcm]

Streams: flat texture payloads (raw + decoded level-0 RGBA), bank 00 sprite sets, the system font table,
ADPCM books / loop states / wave data (and decoded PCM with --pcm), MP3 speech streams.
Any shared run >= cleanroom.taint.FAIL_RUN bytes fails (decoded RGBA: >= 32 texels). Kept facts (code, geometry, animation, text, note
sequences, bank structure) are not scanned.
"""
import json
import os
import sys

import numpy as np

from cleanroom import taint
from . import texlayout as TL
from .romtool import Rom, FONT_START, FONT_END

# Decoded RGBA expands every texel to 4 bytes (a CI4 texel carries 4 bits): the 32-unit rule is applied in
# texels there (32 texels = 128 bytes). 8-texel runs of similar 5-bit colours recur by chance across 16 MB of
# retail pixels; raw payload bytes keep the plain 32-byte rule.
RGBA_RUN = 4 * taint.FAIL_RUN
SPEC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spec")


def streams(r, tex, waves, pcm=False):
    for i, e in enumerate(r.flat):
        if e is None:
            continue
        yield f"flat{i}", e.data
        yield f"flat{i}.rgba", TL.decode_level(e.data, tex[str(i)]).tobytes()
    for i, e in enumerate(r.banks[0][1]):
        if e.data:
            yield f"sprite{i}", e.data
    yield "font", r.rom[FONT_START:FONT_END]
    ents = r.banks[0x17][1]
    ext, tbl = ents[1].data, ents[2].data
    for base, d in waves["waves"].items():
        base = int(base)
        yield f"adpcm@{base:x}", tbl[base:base + d["len"]]
        for bo in d["books"]:
            yield f"book@{bo:x}", ext[bo + 8:bo + 8 + 32 * d["npred"]]
        for lo in d["loops"]:
            yield f"loop@{lo:x}", ext[lo + 12:lo + 44]
        if pcm and d["nframes"]:
            from cleanroom.audio import vadpcm
            import struct
            coefs = list(struct.unpack_from(">%dh" % (16 * d["npred"]), ext, d["books"][0] + 8))
            if any(coefs):
                yield f"pcm@{base:x}", vadpcm.decode(tbl[base:base + d["nframes"] // 16 * 9],
                                                     {"order": 2, "npred": d["npred"], "book": coefs}, d["nframes"]).astype("<i2").tobytes()
    for i, e in enumerate(r.banks[0x16][1]):
        if e.data:
            yield f"mp3_{i}", e.data


def main(argv):
    tex = json.load(open(os.path.join(SPEC, "textures.json")))
    waves = json.load(open(os.path.join(SPEC, "samples.json")))
    pcm = "--pcm" in argv
    ret, cl = Rom(argv[1]), Rom(argv[2])
    index = taint.build_index(s for _, s in streams(ret, tex, waves, pcm))
    n = 0
    groups = {}
    fail = []
    for label, s in streams(cl, tex, waves, pcm):
        n += 1
        import re
        g = re.match(r"[a-z]+", label).group(0) + (".rgba" if label.endswith(".rgba") else "")
        groups.setdefault(g, [0, 0])[0] += 1
        for h in taint.scan(index, [(label, s)]):
            if h[3] >= (RGBA_RUN if label.endswith(".rgba") else taint.FAIL_RUN):
                fail.append(h)
                groups[g][1] += 1
    print(f"taint: {n} streams; FAILING (>= {taint.FAIL_RUN} B shared run): {len(fail)}")
    print("  " + ", ".join(f"{g} {a}/{b} fail" for g, (a, b) in groups.items()))
    for h in sorted(fail, key=lambda h: -h[3])[:10]:
        print("   ", h)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
