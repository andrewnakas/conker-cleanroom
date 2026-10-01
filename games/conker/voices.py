"""Placeholder speech for the 453 MP3 streams (bank 0x16): Piper TTS (offline stock voices, no cloning).

Inputs are facts only (spec/voices.json): per stream its length and bitrate, per phrase its start/end time,
words (speech recognition) and one median pitch. Each phrase is spoken by a stock voice chosen from its pitch
band and placed at its original time, so cutscene timing holds. Recorded takes (games/conker/takes/<id>_<n>.wav,
cut by `practice cut`) win over TTS.

    python -m games.conker.voices build [cache dir]        -> <cache>/<stream>.wav (22.05 kHz mono)
    python -m games.conker.voices practice <rom> <out>     -> DIRTY practice pack (personal use, never published)
    python -m games.conker.voices cut <recording.wav> <track>   -> games/conker/takes/
"""
import io
import json
import os
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "spec")
TAKES = os.path.join(HERE, "takes")
CACHE = os.environ.get("CONKER_VOICE_CACHE", "D:/n64work/conker/voices_cache")
PIPER_DIR = os.environ.get("PIPER_VOICES", "C:/Users/andre/n64work/piper_voices")
HZ = 22050
BANK = 0x16

# pitch band (median Hz of the phrase) -> (track name, Piper model, semitones)
BANDS = [(105, "deep", "en_US-ryan-high", -4.0), (135, "low", "en_US-joe-medium", -2.0),
         (175, "mid", "en_US-ryan-high", 1.5), (230, "high", "en_US-joe-medium", 4.0),
         (300, "female", "en_US-amy-medium", 1.0), (9999, "squeaky", "en_US-kristin-medium", 4.0)]
DEFAULT = ("mid", "en_US-ryan-high", 1.5)


def lines():
    p = os.path.join(SPEC, "voices.json")
    if os.path.exists(p):
        return json.load(open(p))
    out = {}                                  # transcription still running: use what is done
    part = os.path.join(SPEC, "voices.partial.jsonl")
    if os.path.exists(part):
        for ln in open(part):
            k, v = json.loads(ln)
            out[str(k)] = v
    return out


def filler(nbytes, kbps, key):
    """A stream with no transcript yet: faint seeded noise of the same length."""
    n = int(nbytes * 8 / (kbps * 1000) * HZ)
    x = np.random.default_rng(key * 7919 + 17).normal(0, 0.0012, n).astype(np.float32)
    return with_cues(mp3_bytes(x, kbps), key, nbytes)


def band(f0):
    if not f0:
        return DEFAULT
    for top, name, model, semis in BANDS:
        if f0 < top:
            return name, model, semis
    return DEFAULT


_V = {}


def piper(model, text, length):
    from piper import PiperVoice, SynthesisConfig
    if model not in _V:
        _V[model] = PiperVoice.load(os.path.join(PIPER_DIR, model + ".onnx"))
    v = _V[model]
    cfg = SynthesisConfig(length_scale=length, noise_scale=0.7, noise_w_scale=0.8)
    x = np.concatenate([c.audio_float_array for c in v.synthesize(text, syn_config=cfg)]).astype(np.float32)
    return x, v.config.sample_rate


def trim(x, thr=0.006):
    idx = np.nonzero(np.abs(x) > thr)[0]
    return x[max(0, idx[0] - 300):idx[-1] + 300] if len(idx) else x[:0]


def say(text, f0, secs):
    """One phrase fitted to `secs`: float32 at HZ."""
    import librosa
    _, model, semis = band(f0)
    f = 2 ** (semis / 12)
    length = 1.0 * f
    y = np.zeros(0, np.float32)
    for _ in range(4):
        x, sr = piper(model, text, length)
        x = trim(x)
        if not len(x):
            break
        y = librosa.resample(x, orig_sr=sr * f, target_sr=HZ).astype(np.float32)
        if len(y) <= secs * HZ * 1.03 or length < 0.5 * f:
            break
        length *= max(0.5, secs * HZ / len(y) * 0.97)
    peak = np.abs(y).max() if len(y) else 0
    return (y / peak * 0.8).astype(np.float32) if peak else y


def wav_read(path):
    with wave.open(path) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768
        if w.getframerate() != HZ:
            import librosa
            x = librosa.resample(x, orig_sr=w.getframerate(), target_sr=HZ)
        return x


def wav_write(path, x, rate=HZ):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def stream(key, d):
    """Whole stream: phrases at their times over a faint seeded noise floor."""
    n = int(d["secs"] * HZ)
    seed = int(key) * 7919 + 17
    y = np.random.default_rng(seed).normal(0, 0.0012, n).astype(np.float32)
    ph = d["phrases"]
    for k, p in enumerate(ph):
        a = int(p["t0"] * HZ)
        room = (ph[k + 1]["t0"] if k + 1 < len(ph) else d["secs"]) - p["t0"]
        take = os.path.join(TAKES, f"{int(key):03d}_{k:02d}.wav")
        x = wav_read(take) if os.path.exists(take) else say(p["text"], p.get("f0"), max(0.4, min(room, (p["t1"] - p["t0"]) * 1.15)))
        x = x[:max(0, n - a)]
        y[a:a + len(x)] += x
    return np.clip(y, -1, 1)


def mp3_bytes(x, kbps):
    import av
    buf = io.BytesIO()
    ct = av.open(buf, "w", format="mp3", options={"id3v2_version": "0", "write_xing": "0"})
    st = ct.add_stream("libmp3lame", rate=HZ, layout="mono")
    st.bit_rate = kbps * 1000
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)[None, :]
    fr = av.AudioFrame.from_ndarray(pcm, format="s16", layout="mono")
    fr.sample_rate = HZ
    for p in st.encode(fr):
        ct.mux(p)
    for p in st.encode(None):
        ct.mux(p)
    ct.close()
    return buf.getvalue()


BR2 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]


_CUES = None


def with_cues(b, key, limit):
    """Final stream for bank entry `key`: whole MPEG-2 Layer III frames of `b`, with the game's lip-sync cue
    records (kept facts: frame index + 6 bytes, spec/voice_cues.json) re-attached. A cue is `L:` + 6 bytes + NUL
    after a frame whose copyright bit is set. The result stays within `limit` bytes."""
    global _CUES
    if _CUES is None:
        _CUES = json.load(open(os.path.join(SPEC, "voice_cues.json")))
    cues = dict(_CUES.get(str(key), {}).get("cues", []))
    out = bytearray()
    o = k = 0
    while o + 4 <= len(b):
        h = int.from_bytes(b[o:o + 4], "big")
        if h >> 21 != 0x7FF:
            break
        flen = 72 * BR2[(h >> 12) & 15] * 1000 // HZ + ((h >> 9) & 1)
        if flen <= 4 or o + flen > len(b):
            break
        frame = bytearray(b[o:o + flen])
        cue = cues.get(k)
        frame[3] = (frame[3] | 0x08) if cue else (frame[3] & 0xF7)
        if cue:
            frame += b"L:" + bytes.fromhex(cue) + bytes(1)
        if len(out) + len(frame) > limit:
            break
        out += frame
        o += flen
        k += 1
    return bytes(out)


def build(cache=CACHE, only=None):
    os.makedirs(cache, exist_ok=True)
    n = 0
    for key, d in lines().items():
        out = os.path.join(cache, f"{int(key):03d}.wav")
        if (only and key not in only) or (os.path.exists(out) and not only):
            continue
        wav_write(out, stream(key, d))
        n += 1
        if n % 40 == 0:
            print(n, key, flush=True)
    print("voices built:", n)


def encode(cache=CACHE):
    """-> {bank entry index: mp3 bytes}, each no longer than the retail stream."""
    out = {}
    for key, d in lines().items():
        p = os.path.join(cache, f"{int(key):03d}.wav")
        if not os.path.exists(p):
            continue
        b = mp3_bytes(wav_read(p), d["kbps"] or 24)
        out[int(key)] = with_cues(b, int(key), d["bytes"])
    return out


# ------------------------------------------------------------------ practice pack (dirty) / takes (clean)

def plan():
    tracks = {}
    for key, d in lines().items():
        for k, p in enumerate(d["phrases"]):
            tracks.setdefault(band(p.get("f0"))[0], []).append((int(key), k, p))
    out = {}
    for who, items in tracks.items():
        for i in range(0, len(items), 60):
            out[f"{who}{i // 60 + 1}"] = items[i:i + 60]
    return out


def practice(rom, out):
    from .romtool import Rom
    from .voice_spec import load
    import librosa
    ents = Rom(rom).banks[BANK][1]
    os.makedirs(out, exist_ok=True)
    beep = (0.2 * np.sin(2 * np.pi * 880 * np.arange(int(0.08 * HZ)) / HZ)).astype(np.float32)
    script = ["Conker's Bad Fur Day voice practice. One track per voice register: listen, speak after each beep, in character.",
              "Record each track as one file, then: python -m games.conker.voices cut <file> <track>",
              "These clips come from your own ROM: practice only, never share or commit them.", ""]
    dec = {}
    for who, items in sorted(plan().items()):
        parts = []
        script.append(f"== {who}  (practice_{who}_call_and_response.wav)")
        for key, k, p in items:
            if key not in dec:
                dec = {key: librosa.resample(load(ents[key].data)[0], orig_sr=16000, target_sr=HZ)}
            x = dec[key][int(p["t0"] * HZ):int(p["t1"] * HZ)].astype(np.float32)
            gap = np.zeros(int(((p["t1"] - p["t0"]) * 1.5 + 1.5) * HZ), np.float32)
            parts += [x, np.zeros(int(0.3 * HZ), np.float32), beep, gap]
            script.append(f"  {key:03d}_{k:02d}  max {p['t1'] - p['t0']:.1f}s  \"{p['text']}\"")
        wav_write(os.path.join(out, f"practice_{who}_call_and_response.wav"), np.concatenate(parts))
    open(os.path.join(out, "SCRIPT.txt"), "w", encoding="utf8").write("\n".join(script))
    print(f"practice pack: {sum(len(v) for v in plan().values())} phrases, {len(plan())} tracks -> {out}")


def cut(recording, track):
    """Cut the user's recording of one track into takes, using only the spec's phrase lengths."""
    x = wav_read(recording)
    os.makedirs(TAKES, exist_ok=True)
    o = 0
    n = 0
    for key, k, p in plan()[track]:
        ln = int((p["t1"] - p["t0"]) * HZ)
        o += ln + int(0.3 * HZ) + int(0.08 * HZ)
        gap = int(((p["t1"] - p["t0"]) * 1.5 + 1.5) * HZ)
        seg = trim(x[o:o + gap], 0.02)
        if len(seg) > HZ // 10:
            wav_write(os.path.join(TAKES, f"{key:03d}_{k:02d}.wav"), seg / (np.abs(seg).max() or 1) * 0.8)
            n += 1
        o += gap
    print(f"takes: {n} cut for track {track} -> {TAKES}")


if __name__ == "__main__":
    a = sys.argv
    if a[1] == "build":
        build(a[2] if len(a) > 2 else CACHE)
    elif a[1] == "practice":
        practice(a[2], a[3])
    elif a[1] == "cut":
        cut(a[2], a[3])
