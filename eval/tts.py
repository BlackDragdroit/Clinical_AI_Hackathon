"""Synthesise the dictated request items to 16 kHz mono WAV with Piper TTS (CPU, ONNX) -> eval/data/audio/<set>/<id>.wav.

  python -m eval.tts --set test                 (all dictated items of requests_test.jsonl, 120)
  python -m eval.tts --set dev --limit 80       (first 80 dictated items of requests_dev.jsonl)

Voices (rhasspy/piper-voices on Hugging Face, ~63 MB each): de_DE-thorsten-medium for lang de, en_US-lessac-medium for
lang en. Package: piper-tts (>=1.3, the OHF-Voice/piper1-gpl rewrite; ships Windows wheels with espeak-ng built in).
Models are cached under $BB_VOICE_CACHE (default C:/Users/medya/.cache/befundbruecke/voice), never in the repo.
Piper medium voices render at 22.05 kHz; we resample to 16 kHz with libswresample (PyAV, comes with faster-whisper).
onnxruntime is limited to --threads intra-op threads (default 3) because the laptop is shared with other benchmarks.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import wave
from pathlib import Path

CACHE = Path(os.environ.get("BB_VOICE_CACHE", "C:/Users/medya/.cache/befundbruecke/voice"))
os.environ.setdefault("HF_HOME", str(CACHE / "hf"))

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "eval" / "data"
VOICES = {"de": "de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx",
          "en": "en/en_US/lessac/medium/en_US-lessac-medium.onnx"}
TARGET_SR = 16000


def dictated_items(set_name: str, limit: int | None = None) -> list[dict]:
    rows = [json.loads(line) for line in (DATA / f"requests_{set_name}.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()]
    items = [r for r in rows if r.get("style") == "dictated"]
    return items[:limit] if limit else items


def load_voice(lang: str, threads: int = 3):
    import onnxruntime
    from huggingface_hub import hf_hub_download
    from piper import PiperVoice
    from piper.config import PiperConfig

    model = hf_hub_download("rhasspy/piper-voices", VOICES[lang])
    config = hf_hub_download("rhasspy/piper-voices", VOICES[lang] + ".json")
    so = onnxruntime.SessionOptions()
    so.intra_op_num_threads = threads
    so.inter_op_num_threads = 1
    with open(config, encoding="utf-8") as f:
        cfg = PiperConfig.from_dict(json.load(f))
    # PiperVoice.load() has no thread knob, so build the session ourselves (same fields as PiperVoice.load)
    return PiperVoice(config=cfg, session=onnxruntime.InferenceSession(model, sess_options=so, providers=["CPUExecutionProvider"]))


def resample_int16(pcm: bytes, sr: int, target: int = TARGET_SR) -> bytes:
    import av
    import numpy as np

    if sr == target:
        return pcm
    arr = np.frombuffer(pcm, dtype=np.int16).reshape(1, -1)
    frame = av.AudioFrame.from_ndarray(arr, format="s16", layout="mono")
    frame.sample_rate = sr
    rs = av.AudioResampler(format="s16", layout="mono", rate=target)
    out = [f.to_ndarray().reshape(-1) for f in rs.resample(frame)] + [f.to_ndarray().reshape(-1) for f in rs.resample(None)]
    return np.concatenate(out).astype(np.int16).tobytes() if out else b""


def synthesise(voice, text: str) -> tuple[bytes, int]:
    chunks, sr = [], None
    for ch in voice.synthesize(text):
        chunks.append(ch.audio_int16_bytes)
        sr = ch.sample_rate
    return b"".join(chunks), sr or voice.config.sample_rate


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="test", choices=["test", "dev"])
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--threads", type=int, default=3)
    ap.add_argument("--force", action="store_true", help="re-synthesise existing files")
    a = ap.parse_args()

    items = dictated_items(a.set, a.limit)
    out_dir = DATA / "audio" / a.set
    out_dir.mkdir(parents=True, exist_ok=True)
    voices: dict = {}
    t_all, n_new, dur = time.perf_counter(), 0, 0.0
    for it in items:
        path = out_dir / f"{it['id']}.wav"
        if path.exists() and not a.force:
            continue
        lang = it.get("lang", "de")
        if lang not in voices:
            voices[lang] = load_voice(lang, a.threads)
        pcm, sr = synthesise(voices[lang], it["text"])
        pcm = resample_int16(pcm, sr)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(TARGET_SR)
            w.writeframes(pcm)
        n_new += 1
        dur += len(pcm) / 2 / TARGET_SR
    el = time.perf_counter() - t_all
    print(f"{a.set}: {len(items)} dictated items, {n_new} synthesised ({dur:.0f} s audio) in {el:.0f} s -> {out_dir}")


if __name__ == "__main__":
    main()
