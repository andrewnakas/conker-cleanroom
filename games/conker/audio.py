"""Conker sound bank (bank 0x17: 0 = B1 control, 1 = bank objects, 2 = wave table, 3 = S1 sequences).

Dirty room:  python -m games.conker.audio spec <rom> <audio_graph.json> games/conker/spec/samples.json
   audio_graph.json = the decomp's `parse_sound_bank_graph` manifest (object offsets inside entry 1).
   Kept per unique sample: tbl offset/length, sample count, loop points, coarse spectral outline (<= 24 frames),
   median pitch, and where its books / loop states live.
Clean room:  build(retail entry 1, spec) -> (entry 1 with our books + loop states, new wave table).
   Bank structure (envelopes, key maps, tuning), like the note sequences, is kept.
"""
import json
import os
import struct
import sys
from multiprocessing import Pool

import numpy as np

from cleanroom.audio import descriptor, vadpcm
from cleanroom.audio.pitch import median_f0
from cleanroom.decomp import gen

RATE = 22050
BANK = 0x17


def k_predictors(x, k=4):
    """Our own predictor set: k-means over per-16-sample 2nd-order LPC fits of our own waveform."""
    fits = []
    for s in range(2, len(x) - 16, 16):
        y, p1, p2 = x[s:s + 16], x[s - 1:s + 15], x[s - 2:s + 14]
        if (y ** 2).sum() < 1e3:
            continue
        a, *_ = np.linalg.lstsq(np.stack([p1, p2], 1), y, rcond=None)
        fits.append(a)
        if len(fits) >= 400:
            break
    base = [(1.0, 0.0), (1.8, -0.82), (0.5, 0.0), (1.4, -0.5)]
    if len(fits) < k:
        return base[:k]
    f = np.clip(np.asarray(fits), [-1.95, -0.98], [1.95, 0.98])
    pick = np.linspace(0, len(f) - 1, k).astype(int)
    c = f[pick][np.argsort(f[pick, 0])].copy()
    for _ in range(12):
        lab = np.argmin(((f[:, None, :] - c[None]) ** 2).sum(-1), 1)
        for j in range(k):
            if (lab == j).any():
                c[j] = f[lab == j].mean(0)
    out = []
    for a1, a2 in c:
        a2 = float(np.clip(a2, -0.98, 0.98))
        out.append((float(np.clip(a1, -(1 - a2) + 0.02, (1 - a2) - 0.02)), a2))
    return out


def _describe(job):
    base, raw, coefs, nf = job
    book = {"order": 2, "npred": len(coefs) // 16, "book": coefs}
    pcm = vadpcm.decode(raw, book, nf).astype(np.float64)
    d = {"desc": descriptor.describe(pcm, RATE)}
    f0 = median_f0((pcm[:RATE * 4] / 32768).astype(np.float32), RATE)
    if f0:
        d["f0"] = round(float(f0), 1)
    return base, d


def spec(rom_path, graph_path, out):
    from .romtool import Rom
    r = Rom(rom_path)
    ents = r.banks[BANK][1]
    ext, tbl = ents[1].data, ents[2].data
    g = json.load(open(graph_path))
    wts, books, loops = g["wavetables"], g["adpcm_books"], g["loops"]
    facts, jobs = {}, []
    for s in g["samples"]:
        base = int(s["base"], 16)
        ws = [wts[i] for i in s["wavetable_indices"]]
        assert s["kind"] == "adpcm"
        n9 = s["runtime_payload_length"] // 9
        b0 = books[ws[0]["book_index"]]
        bo = sorted({int(books[w["book_index"]]["offset"], 16) for w in ws})
        for o in bo:
            assert struct.unpack_from(">ii", ext, o) == (2, b0["predictor_count"])
        d = {"len": s["stored_length"], "nframes": n9 * 16, "npred": b0["predictor_count"], "books": bo,
             "loops": sorted({int(loops[w["loop_index"]]["offset"], 16) for w in ws if w["loop_index"] is not None})}
        lp = [loops[w["loop_index"]] for w in ws if w["loop_index"] is not None]
        if lp:
            d["loop"] = [lp[0]["start_sample"], lp[0]["end_sample"], lp[0]["count"]]
        facts[base] = d
        jobs.append((base, tbl[base:base + n9 * 9], b0["coefficients"], n9 * 16))
    with Pool(4) as p:
        for k, (base, d) in enumerate(p.imap_unordered(_describe, jobs, chunksize=8)):
            facts[base].update(d)
    json.dump({"tbl_len": len(tbl), "ext_len": len(ext), "waves": facts}, open(out, "w"), separators=(",", ":"))
    tot = sum(d["nframes"] for d in facts.values())
    print(f"samples: {len(facts)} waves, {tot / RATE / 60:.1f} min, tbl {len(tbl)} B -> {out} ({os.path.getsize(out) // 1024} KB)")


def _make(job):
    base, d = job
    nf = d["nframes"]
    if nf == 0:
        return base, b"", None, None
    x = descriptor.synthesize(d["desc"], nf, RATE, seed=gen.h32("conker", base))
    x = np.pad(np.asarray(x, np.float32)[:nf], (0, max(0, nf - len(x))))
    st = en = cnt = 0
    if "loop" in d:
        st, en, cnt = d["loop"]
        if cnt and en > st + 16:
            x = descriptor.make_loop_seamless(x, st, min(en, nf))
    dither = np.random.default_rng(gen.h32("dither", base)).integers(-1, 2, nf)
    pcm = np.clip(np.round(np.clip(x, -1, 1) * 30000) + dither, -32768, 32767).astype(np.int16)
    book = vadpcm.make_book(k_predictors(pcm.astype(np.float64), d["npred"]))
    data, _, dec = vadpcm.encode(pcm, book)
    data = bytes(data[:d["len"]]) + bytes(max(0, d["len"] - len(data)))
    vals = struct.pack(">%dh" % len(book["book"]), *book["book"])
    state = struct.pack(">16h", *[int(v) for v in vadpcm.loop_state(dec, st)]) if cnt else None
    return base, data, vals, state


def build(ext, spec_dir, cache=None, procs=4):
    """-> (entry 1 bytes, wave table bytes). cache: optional .npz-like pickle path to reuse the synthesis."""
    import pickle
    S = json.load(open(os.path.join(spec_dir, "samples.json")))
    key = os.path.getmtime(os.path.join(spec_dir, "samples.json"))
    res = None
    if cache and os.path.exists(cache):
        k, res = pickle.load(open(cache, "rb"))
        if k != key:
            res = None
    if res is None:
        jobs = [(int(b), d) for b, d in S["waves"].items()]
        jobs.sort(key=lambda j: -j[1]["nframes"])
        with Pool(procs) as p:
            res = p.map(_make, jobs, chunksize=4)
        if cache:
            pickle.dump((key, res), open(cache, "wb"))
    ext = bytearray(ext)
    assert len(ext) == S["ext_len"]
    tbl = bytearray(S["tbl_len"])
    for base, data, vals, state in res:
        d = S["waves"][str(base)]
        tbl[base:base + d["len"]] = data
        for bo in d["books"]:
            ext[bo + 8:bo + 8 + 16 * 2 * d["npred"]] = vals if vals else bytes(32 * d["npred"])
        for lo in d["loops"]:
            ext[lo + 12:lo + 44] = state if state else bytes(32)
    return bytes(ext), bytes(tbl)


if __name__ == "__main__":
    if sys.argv[1] == "spec":
        spec(sys.argv[2], sys.argv[3], sys.argv[4])
    elif sys.argv[1] == "build":      # warm the synthesis cache: build <rom> <cache.pkl>
        from .romtool import Rom
        ext = Rom(sys.argv[2]).banks[BANK][1][1].data
        e, t = build(ext, os.path.join(os.path.dirname(os.path.abspath(__file__)), "spec"), cache=sys.argv[3])
        print(f"audio: ext {len(e)} B, tbl {len(t)} B, nonzero {sum(1 for b in t[::4096] if b)}")
