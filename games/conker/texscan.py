"""Dirty room: find how every flat texture id is used, from display lists in the asset banks and game data.

A flat reference is `FD ss 00 00 | (mode << 22) | id` (mode 0 pixels, 1 = trailing 0x200 TLUT, 2 = trailing 0x20 TLUT).
After a pixel reference we read the following SetTile (F5) / SetTileSize (F2) / LoadBlock (F3) / LoadTile (F4) commands.

    python -m games.conker.texscan <rom> <out usages.json>

Output per id: decoded size, palette modes seen, and the distinct usages
{tiles: [[tile, fmt, siz, line, tmem, w, h, cms, cmt, masks, maskt]], texels, dxt, n}.
"""
import collections
import json
import struct
import sys

from .romtool import Rom, FLAT_COUNT

STOP = {0x01, 0x05, 0x06, 0x07, 0xDF, 0xDE} | set(range(0x10, 0x20))


def scan_blob(blob, where, uses, pals):
    n = len(blob) // 4
    words = struct.unpack_from(f">{n}I", blob, 0)
    for i in range(0, n - 1):
        w0 = words[i]
        if w0 & 0xFF00FFFF != 0xFD000000:
            continue
        w1 = words[i + 1]
        mode, idx = w1 >> 22, w1 & 0x3FFFFF
        if mode > 2 or idx >= FLAT_COUNT:
            continue
        if mode:
            pals[idx][mode] += 1
            continue
        tiles = {}
        texels = dxt = None
        j = i + 2
        steps = 0
        while j + 1 < n and steps < 40:
            c0, c1 = words[j], words[j + 1]
            op = c0 >> 24
            if op == 0xFD or op in STOP:
                break
            if op == 0xF5:
                t = (c1 >> 24) & 7
                tiles.setdefault(t, {}).update(fmt=(c0 >> 21) & 7, siz=(c0 >> 19) & 3, line=(c0 >> 9) & 0x1FF,
                                               tmem=c0 & 0x1FF, pal=(c1 >> 20) & 15, cmt=(c1 >> 18) & 3,
                                               maskt=(c1 >> 14) & 15, cms=(c1 >> 8) & 3, masks=(c1 >> 4) & 15)
            elif op == 0xF2:
                t = (c1 >> 24) & 7
                tiles.setdefault(t, {}).update(w=(((c1 >> 12) & 0xFFF) - ((c0 >> 12) & 0xFFF)) // 4 + 1,
                                               h=((c1 & 0xFFF) - (c0 & 0xFFF)) // 4 + 1)
            elif op == 0xF3:
                texels, dxt = ((c1 >> 12) & 0xFFF) + 1, c1 & 0xFFF
            elif op == 0xF4:
                texels, dxt = -1, -1
            elif op not in (0xE6, 0xE7, 0xE8, 0xF0, 0xD7, 0xFC, 0xE2, 0xE3, 0xEF, 0xD9, 0xFA, 0xFB, 0xDB, 0xDA, 0xDC, 0x00):
                break
            j += 2
            steps += 1
        key = (tuple(sorted((t, d.get("fmt", -1), d.get("siz", -1), d.get("line", -1), d.get("tmem", -1), d.get("w", 0),
                             d.get("h", 0), d.get("cms", 0), d.get("cmt", 0), d.get("masks", 0), d.get("maskt", 0),
                             d.get("pal", 0)) for t, d in tiles.items())), texels, dxt, (w0 >> 16) & 0xFF)
        uses[idx][key] += 1


def main(argv):
    r = Rom(argv[1])
    uses = collections.defaultdict(collections.Counter)
    pals = collections.defaultdict(collections.Counter)
    for b, (fl, ents) in enumerate(r.banks):
        if fl:
            continue
        for i, e in enumerate(ents):
            if e.data:
                scan_blob(e.data, (b, i), uses, pals)
    scan_blob(bytes(r.gdata), "data", uses, pals)
    scan_blob(b"".join(r.code_chunks), "code", uses, pals)
    out = {}
    for idx, e in enumerate(r.flat):
        if e is None:
            continue
        out[idx] = dict(size=len(e.data), pal={str(k): v for k, v in pals[idx].items()},
                        uses=[dict(tiles=[list(t) for t in k[0]], texels=k[1], dxt=k[2], img=k[3], n=n)
                              for k, n in uses[idx].most_common()])
    json.dump(out, open(argv[2], "w"))
    have = sum(1 for v in out.values() if v["uses"])
    sized = sum(1 for v in out.values() if any(any(t[5] and t[6] for t in u["tiles"]) for u in v["uses"]))
    print(f"flat ids {len(out)}: referenced {have}, with a sized tile {sized}, palette-only {sum(1 for v in out.values() if v['pal'] and not v['uses'])}")
    miss = collections.Counter(v["size"] for v in out.values() if not v["uses"])
    print("unreferenced by size:", miss.most_common(20))


if __name__ == "__main__":
    main(sys.argv)
