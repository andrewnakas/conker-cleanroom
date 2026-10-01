"""DIRTY ROOM: the 453 MP3 speech streams (bank 0x16) -> spec/voices.json.

Facts only: per stream its length, sample rate, bitrate and byte size, and per recognised phrase its start/end
time, the words (speech recognition) and one median pitch. The audio itself is never copied.

    python -m games.conker.voice_spec <rom> games/conker/spec [cuda|cpu] [model]
"""
import io
import json
import os
import struct
import sys

import av
import numpy as np

from cleanroom.audio.pitch import median_f0

BANK = 0x16
BR2 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]


def load(data):
    ct = av.open(io.BytesIO(data), format="mp3")
    s = ct.streams.audio[0]
    rate = s.rate
    res = av.AudioResampler(format="flt", layout="mono", rate=16000)
    chunks, n = [], 0
    for pkt in ct.demux(s):
        try:
            frames = pkt.decode()
        except av.error.InvalidDataError:
            continue
        for fr in frames:
            n += fr.samples
            for r in res.resample(fr):
                chunks.append(r.to_ndarray().ravel())
    for r in res.resample(None):
        chunks.append(r.to_ndarray().ravel())
    return np.concatenate(chunks) if chunks else np.zeros(0, np.float32), rate, n


def main(argv):
    from .romtool import Rom
    from faster_whisper import WhisperModel
    rom, spec = argv[:2]
    dev = argv[2] if len(argv) > 2 else "cuda"
    name = argv[3] if len(argv) > 3 else "medium.en"
    model = WhisperModel(name, device=dev, compute_type="float16" if dev == "cuda" else "int8", cpu_threads=4)
    ents = Rom(rom).banks[BANK][1]
    part = os.path.join(spec, "voices.partial.jsonl")
    out = {}
    if os.path.exists(part):
        for ln in open(part):
            k, v = json.loads(ln)
            out[int(k)] = v
    for i, e in enumerate(ents):
        if not e.data or i in out:
            continue
        h = struct.unpack_from(">I", e.data, 0)[0]
        x, rate, n = load(e.data)
        segs, _ = model.transcribe(x, language="en", beam_size=5, vad_filter=len(x) > 16000 * 12,
                                   condition_on_previous_text=False)
        phrases = []
        for s in segs:
            t = s.text.strip()
            if not t or s.no_speech_prob > 0.8:
                continue
            a, b = int(s.start * 16000), int(s.end * 16000)
            f0 = median_f0(x[a:b].astype(np.float32), 16000) if b - a > 1600 else None
            phrases.append({"t0": round(s.start, 2), "t1": round(s.end, 2), "text": t,
                            "f0": round(float(f0), 1) if f0 else None})
        rms = float(np.sqrt((x ** 2).mean())) if len(x) else 0.0
        out[i] = {"secs": round(n / rate, 3), "rate": rate, "kbps": BR2[(h >> 12) & 15], "bytes": len(e.data),
                  "flags": e.flags, "rms": round(rms, 4), "phrases": phrases}
        with open(part, "a") as fp:
            fp.write(json.dumps([i, out[i]]) + "\n")
        if i % 25 == 0:
            print(i, out[i]["secs"], [p["text"] for p in phrases][:2], flush=True)
    json.dump({str(k): out[k] for k in sorted(out)}, open(os.path.join(spec, "voices.json"), "w"), indent=0)
    print("voices:", len(out), "streams,", round(sum(v["secs"] for v in out.values()) / 60, 1), "min,",
          sum(len(v["phrases"]) for v in out.values()), "phrases")


if __name__ == "__main__":
    main(sys.argv[1:])
