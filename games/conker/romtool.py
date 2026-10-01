"""Conker's BFD (US) ROM container: parse and rebuild.

Layout (facts from the decomp's docs/rzip-assets.md and scripts/rzip_archive.py):
  0x040F10  RLE font table (95 glyphs)
  0x042450  game archive: [data offset][XOR'd code chunk offsets][4K RZIP code chunks][pad][RZIP data chunk][pad]
  0x1A37E0  flat RZIP stream (textures); u16 compressed sizes live in game data at D_80091D20 (7762 runtime ids)
  0xAB1950  bank table (offset,size|flags) -> per-bank entry tables (offset, len | flags<<28; 1 = RZIP, 8 = last), entries 8-aligned

RZIP chunk = u32 decoded size + raw deflate.

    python -m games.conker.romtool selftest <rom>            identity rebuild must be byte-identical
    python -m games.conker.romtool recompress <rom> <out>    recompress every chunk with our deflate (emulator test)
"""
import hashlib
import struct
import sys
import zlib

RETAIL_SHA1 = "4cbadd3c4e0729dec46af64ad018050eada4f47a"
FONT_START, FONT_END = 0x40F10, 0x42450
GAME_START, GAME_END = 0x42450, 0x19EA88
FLAT_START, TABLE_START = 0x1A37E0, 0xAB1950
OFFSET_XOR = 0x8039CCCA
DATA_VRAM = 0x80082B20
FLAT_SIZE_TABLE = 0x80091D20 - DATA_VRAM
FLAT_COUNT = 0x1E52
CRC_START, CRC_END = 0x1000, 0x101000
CIC_6105_SEED = 0xDF26F436


def unrzip(blob):
    """-> (data, consumed)"""
    size = struct.unpack_from(">I", blob, 0)[0]
    d = zlib.decompressobj(wbits=-15)
    data = d.decompress(blob[4:]) + d.flush()
    assert d.eof and len(data) == size, "bad RZIP chunk"
    return data, len(blob) - len(d.unused_data)


_RZ = None


def rzip(data):
    """Rare's own deflate (gzip 1.2.4, tools/rarezip): reproduces most retail chunks byte for byte.
    zlib streams are not safe for the game's inflate (fixed Huffman table buffer, see the BK notes)."""
    global _RZ
    import ctypes
    import os
    if _RZ is None:
        _RZ = ctypes.CDLL(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools", "rarezip", "rarezip.dll"))
        _RZ.bk_zip.restype = ctypes.c_size_t
        _RZ.bk_zip.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_size_t]
    data = bytes(data)
    cap = len(data) + len(data) // 8 + 0x1000
    out = ctypes.create_string_buffer(cap)
    n = _RZ.bk_zip(data, len(data), out, cap)
    return struct.pack(">I", len(data)) + out.raw[6:n]


def crc_6105(rom):
    rol = lambda v, n: ((v << n) | (v >> (32 - n))) & 0xFFFFFFFF if n else v
    t1 = t2 = t3 = t4 = t5 = t6 = CIC_6105_SEED
    M = 0xFFFFFFFF
    for off in range(CRC_START, CRC_END, 4):
        v = struct.unpack_from(">I", rom, off)[0]
        if t6 + v > M:
            t4 = (t4 + 1) & M
        t6 = (t6 + v) & M
        t3 ^= v
        r = rol(v, v & 0x1F)
        t5 = (t5 + r) & M
        t2 ^= r if t2 > v else t6 ^ v
        b = struct.unpack_from(">I", rom, 0x750 + (off & 0xFF))[0]
        t1 = (t1 + (b ^ v)) & M
    return t6 ^ t4 ^ t3, t5 ^ t2 ^ t1


class Entry:
    __slots__ = ("flags", "raw", "data", "dirty")

    def __init__(self, flags, raw, data):
        self.flags, self.raw, self.data, self.dirty = flags, raw, data, False

    @property
    def compressed(self):
        return bool(self.flags & 1)


class Rom:
    def __init__(self, path):
        self.rom = rom = open(path, "rb").read()
        assert rom[:4] == b"\x80\x37\x12\x40", "need a big-endian .z64"
        # --- game archive
        g = rom[GAME_START:GAME_END]
        self.data_start = struct.unpack_from(">I", g, 0)[0]
        offs = []
        for i in range(1, len(g) // 4):
            v = struct.unpack_from(">I", g, i * 4)[0]
            if v == 0:
                break
            offs.append(v ^ OFFSET_XOR)
        self.code_offs = offs
        self.code_chunks = [unrzip(g[a:b])[0] for a, b in zip(offs, offs[1:])]
        self.code_dirty = False
        self.gdata, used = unrzip(g[self.data_start:])
        self.gdata = bytearray(self.gdata)
        self.gdata_orig = bytes(self.gdata)
        self.data_end = self.data_start + used
        # --- flat stream, by runtime id
        sizes = struct.unpack_from(f">{FLAT_COUNT}H", self.gdata, FLAT_SIZE_TABLE)
        self.flat = []
        o = FLAT_START
        for s in sizes:
            if s == 0:
                self.flat.append(None)
                continue
            raw = rom[o:o + s]
            data, used = unrzip(raw)
            assert used == s
            self.flat.append(Entry(1, raw, data))
            o += s
        self.flat_end = o
        assert all(b == 0 for b in rom[o:TABLE_START])
        # --- banks
        n = struct.unpack_from(">I", rom, TABLE_START)[0] // 8
        self.banks = []
        for b in range(n):
            rel, sf = struct.unpack_from(">II", rom, TABLE_START + b * 8)
            start, size, bflags = TABLE_START + rel, sf & 0x0FFFFFFF, sf >> 28
            if bflags:
                self.banks.append((bflags, rom[start:start + size]))
                continue
            cnt = struct.unpack_from(">I", rom, start)[0] // 8
            ents = []
            for i in range(cnt):
                erel, lf = struct.unpack_from(">II", rom, start + i * 8)
                ln, fl = lf & 0x0FFFFFFF, lf >> 28
                raw = rom[start + erel:start + erel + ln]
                data = unrzip(raw)[0] if (fl & 1 and ln) else raw
                ents.append(Entry(fl, raw, data))
            self.banks.append((0, ents))
        self.assets_end = start + size
        self.fonts = rom[FONT_START:FONT_END]

    # --- edits
    def set_flat(self, i, data):
        e = self.flat[i]
        if bytes(data) != e.data:
            assert len(data) == len(e.data), f"flat {i}: size changed"
            e.data, e.dirty = bytes(data), True

    def set_bank(self, b, i, data):
        e = self.banks[b][1][i]
        if bytes(data) != e.data:
            e.data, e.dirty = bytes(data), True

    # --- build
    def build(self, recompress=()):
        """recompress: subset of {'flat','banks','code','data'} to force through our compressor (tests)."""
        out = bytearray(self.rom)
        def enc(e, force):
            if (e.dirty or force) and e.compressed and e.data:
                return rzip(e.data)
            return e.data if e.dirty else e.raw
        # flat
        chunks, sizes = [], []
        for e in self.flat:
            c = enc(e, 'flat' in recompress) if e else b""
            assert len(c) < 0x10000, "flat chunk over 64K"
            chunks.append(c)
            sizes.append(len(c))
        stream = b"".join(chunks)
        cap = TABLE_START - 15 - FLAT_START
        assert len(stream) <= cap, f"flat stream {len(stream) - cap} bytes too large"
        out[FLAT_START:TABLE_START] = stream + bytes(TABLE_START - FLAT_START - len(stream))
        struct.pack_into(f">{FLAT_COUNT}H", self.gdata, FLAT_SIZE_TABLE, *sizes)
        # game archive
        if 'code' in recompress or 'data' in recompress or self.code_dirty or bytes(self.gdata) != self.gdata_orig:
            g = bytearray(out[GAME_START:GAME_END])
            if 'code' in recompress or self.code_dirty:
                pos = self.code_offs[0]
                offs = [pos]
                body = b""
                for c in self.code_chunks:
                    z = rzip(c)
                    body += z
                    pos += len(z)
                    offs.append(pos)
                assert pos <= self.data_start, "code chunks overflow"
                g[self.code_offs[0]:self.data_start] = body + bytes(self.data_start - self.code_offs[0] - len(body))
                for i, o in enumerate(offs):
                    struct.pack_into(">I", g, 4 + i * 4, o ^ OFFSET_XOR)
            z = rzip(bytes(self.gdata))
            assert self.data_start + len(z) <= len(g), "game data overflow"
            g[self.data_start:] = z + bytes(len(g) - self.data_start - len(z))
            out[GAME_START:GAME_END] = g
        out[FONT_START:FONT_END] = self.fonts
        # banks
        n = len(self.banks)
        pos = TABLE_START + n * 8
        table = b""
        blob = b""
        for bflags, body in self.banks:
            start = pos + len(blob)
            if bflags:
                b = body
            else:
                cur = len(body) * 8
                tab, parts = b"", []
                for e in body:
                    c = enc(e, 'banks' in recompress)
                    pad = -cur % 8
                    parts.append(bytes(pad))
                    cur += pad
                    tab += struct.pack(">II", cur, (e.flags << 28) | len(c))
                    parts.append(c)
                    cur += len(c)
                b = tab + b"".join(parts)
                b += bytes(-len(b) % 8)
            table += struct.pack(">II", start - TABLE_START, (bflags << 28) | len(b))
            blob += b
        end = pos + len(blob)
        assert end <= len(out), "banks overflow the ROM"
        fill = self.rom[self.assets_end:self.assets_end + 1] or b"\xff"
        out[TABLE_START:max(end, self.assets_end)] = table + blob + fill * max(0, self.assets_end - end)
        c1, c2 = crc_6105(out)
        struct.pack_into(">II", out, 0x10, c1, c2)
        return bytes(out)


def main(argv):
    r = Rom(argv[2])
    if argv[1] == "selftest":
        b = r.build()
        ok = b == r.rom
        print("identity rebuild:", "OK" if ok else "MISMATCH", hashlib.sha1(b).hexdigest())
        if not ok:
            d = [i for i in range(0, len(b), 4096) if b[i:i + 4096] != r.rom[i:i + 4096]]
            first = next(i for i in range(d[0], d[0] + 4096) if b[i] != r.rom[i])
            print(f"{len(d)} differing 4K blocks, first diff at 0x{first:X}")
        print(f"flat {sum(e is not None for e in r.flat)} entries, end 0x{r.flat_end:X}; "
              f"banks {len(r.banks)}; assets end 0x{r.assets_end:X}; code chunks {len(r.code_chunks)}")
    elif argv[1] == "recompress":
        b = r.build(recompress=set((argv[4] if len(argv) > 4 else 'flat,banks,code,data').split(',')))
        open(argv[3], "wb").write(b)
        print("recompressed ->", argv[3], hashlib.sha1(b).hexdigest())


if __name__ == "__main__":
    main(sys.argv)
