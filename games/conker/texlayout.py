"""Texture payload layouts for the flat archive (shared by the dirty spec extractor and the clean generator).

A flat payload = pixel levels (TMEM image, LoadBlock dxt=0: odd rows have their 32-bit halves exchanged)
followed by an optional trailing palette (0x200 bytes = CI8, 0x20 = CI4; RGBA5551).

layout = {"fmt","siz","pal": 0|32|512, "swap": bool, "levels": [[offset, stride, w, h], ...]}
"""
import numpy as np

from cleanroom.gfx import texfmt

BPP = {0: 4, 1: 8, 2: 16, 3: 32}


def stride_for(w, siz):
    return (w * BPP[siz] + 63) // 64 * 8


def mip_levels(w, h, siz, full=True):
    out, off = [], 0
    while True:
        s = stride_for(w, siz)
        out.append([off, s, w, h])
        off += s * h
        if not full or min(w, h) <= 2:
            break
        w, h = max(1, w // 2), max(1, h // 2)
    return out, off


def unswap(buf, stride, h, siz):
    """Exchange the halves of each 8-byte group (16 for 32-bit) on odd rows. Its own inverse."""
    a = np.frombuffer(bytes(buf), np.uint8)[:stride * h].reshape(h, stride).copy()
    g = 16 if siz == 3 else 8
    if stride % g:
        return a
    odd = a[1::2].reshape(-1, stride // g, 2, g // 2)
    a[1::2] = odd[:, :, ::-1, :].reshape(-1, stride)
    return a


def palette(data, lay):
    if not lay["pal"]:
        return None
    return texfmt.decode(data[len(data) - lay["pal"]:], lay["pal"] // 2, 1, texfmt.RGBA, texfmt.B16)[0]


def decode_level(data, lay, k=0, pal=None):
    off, stride, w, h = lay["levels"][k]
    siz = lay["siz"]
    buf = data[off:off + stride * h]
    if len(buf) < stride * h:
        buf = buf + bytes(stride * h - len(buf))
    rows = unswap(buf, stride, h, siz) if lay["swap"] else np.frombuffer(buf, np.uint8).reshape(h, stride)
    wpad = stride * 8 // BPP[siz]
    if pal is None:
        pal = palette(data, lay)
    img = texfmt.decode(rows.tobytes(), wpad, h, lay["fmt"], siz, pal)
    return img[:, :w]


def encode_level(rgba_or_idx, lay, k=0):
    """rgba (h, w, 4) or, for CI, an index image (h, w). Returns the stored bytes of that level."""
    off, stride, w, h = lay["levels"][k]
    siz = lay["siz"]
    wpad = stride * 8 // BPP[siz]
    a = np.asarray(rgba_or_idx)
    if lay["fmt"] == texfmt.CI:
        full = np.zeros((h, wpad, 4), np.uint8)
        full[:, :w, 0] = a
        full[:, w:, 0] = a[:, -1:]
    else:
        full = np.zeros((h, wpad, 4), np.uint8)
        full[:, :w] = a
        full[:, w:] = a[:, -1:]
    raw = texfmt.encode(full, lay["fmt"], siz)
    rows = unswap(raw, stride, h, siz) if lay["swap"] else np.frombuffer(raw, np.uint8).reshape(h, stride)
    return rows.tobytes()
