"""Voice evaluation of the request job: synthetic dictation (eval/tts.py) -> CPU ASR -> request_job (rules only) -> gold.

  python -m eval.voice_eval run --set test --backend parakeet [--limit 60] [--threads 3] [--reuse]
  python -m eval.voice_eval run --set test --backend text          (perfect-ASR baseline: the item's own text)
  python -m eval.voice_eval report                                  (eval/VOICE.md from eval/results/voice_*.json)

Backends (all CPU, models cached under $BB_VOICE_CACHE, default C:/Users/medya/.cache/befundbruecke/voice):
  parakeet          onnx-asr "nemo-parakeet-tdt-0.6b-v3", int8 (istupakov/parakeet-tdt-0.6b-v3-onnx); no language/prompt
  whisper-small     faster-whisper "small" (Systran/faster-whisper-small), compute_type int8
  whisper-turbo-de  faster-whisper on cstr/whisper-large-v3-turbo-german-int8_float32 (CT2 int8 conversion of
                    primeline/whisper-large-v3-turbo-german)
  text              no ASR: the request job runs on the item's text (upper bound; shows what ASR costs)
Whisper gets the item's language and an initial_prompt with domain words.

Scoring is copied from eval/run_eval.py::eval_requests (recipient/contact/patient/doc_type/ready, full, silent error,
wrong patient). WER: lower-case, punctuation -> space, word-level Levenshtein vs the item's text (which is written the
way it is dictated: "punkt", "at", spelled digits) -- so an ASR that writes "0660..." or "a.b@c.example" is charged
WER for a correct hearing. Contact exact is the field that matters.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
from pathlib import Path

CACHE = Path(os.environ.get("BB_VOICE_CACHE", "C:/Users/medya/.cache/befundbruecke/voice"))
os.environ.setdefault("HF_HOME", str(CACHE / "hf"))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "eval" / "data"
RESULTS = ROOT / "eval" / "results"

BACKENDS = {
    "text": "no ASR (item text = perfect transcript)",
    "parakeet": "Parakeet TDT 0.6B v3 int8, onnx-asr (istupakov/parakeet-tdt-0.6b-v3-onnx)",
    "whisper-small": "Whisper small int8, faster-whisper (Systran/faster-whisper-small)",
    "whisper-turbo-de": "Whisper large-v3-turbo German int8, faster-whisper (cstr/whisper-large-v3-turbo-german-int8_float32)",
}
WHISPER_REPO = {"whisper-small": "small", "whisper-turbo-de": "cstr/whisper-large-v3-turbo-german-int8_float32"}
PROMPT = {"de": "Gerinnung, INR, Blutbild, Entlassungsbericht, punkt, at, minus, Doktor.",
          "en": "Gerinnung, INR, Blutbild, Entlassungsbericht, dot, at, dash, Doctor."}


# ---------------------------------------------------------------- statistics (copied from eval/run_eval.py)
def _binom_cdf(k: int, n: int, p: float) -> float:
    if p <= 0:
        return 1.0
    if p >= 1:
        return 0.0 if k < n else 1.0
    return sum(math.exp(math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * math.log(p) + (n - i) * math.log1p(-p))
               for i in range(k + 1))


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    def solve(f, lo=0.0, hi=1.0):
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if f(mid) else (lo, mid)
        return (lo + hi) / 2
    lower = 0.0 if k == 0 else solve(lambda p: 1 - _binom_cdf(k - 1, n, p) < alpha / 2)
    upper = 1.0 if k == n else solve(lambda p: _binom_cdf(k, n, p) > alpha / 2)
    return lower, upper


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def rate(k: int, n: int, exact: bool = False) -> dict:
    lo, hi = clopper_pearson(k, n) if exact else wilson(k, n)
    return {"k": k, "n": n, "p": k / n if n else None, "lo": lo, "hi": hi}


def pct(q: list[float], p: float) -> float | None:
    if not q:
        return None
    q = sorted(q)
    return q[min(len(q) - 1, int(round(p * (len(q) - 1))))]


# ---------------------------------------------------------------- WER
def words(s: str) -> list[str]:
    return re.sub(r"[^\w]+", " ", (s or "").lower()).split()


def edit_distance(a: list[str], b: list[str]) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def wer(ref: str, hyp: str) -> tuple[int, int]:
    r = words(ref)
    return edit_distance(r, words(hyp)), len(r)


def clean(hyp: str) -> str:
    """--clean: drop the punctuation ASR inserts between dictated tokens ("Katharina, punkt, Weber, At, ...") but keep
    dots inside tokens and after digits ("a.b", "19. Juni"). An experiment for what a tolerant normaliser would recover."""
    hyp = re.sub(r"[,;:!?]", " ", hyp)
    hyp = re.sub(r"(?<=[^\W\d])\.(?=\s|$)", " ", hyp)
    return re.sub(r"\s+", " ", hyp).strip()


# ---------------------------------------------------------------- ASR backends
class Asr:
    def __init__(self, backend: str, threads: int):
        self.backend, self.threads = backend, threads
        t0 = time.perf_counter()
        if backend == "parakeet":
            import onnx_asr
            import onnxruntime as rt
            so = rt.SessionOptions()
            so.intra_op_num_threads = threads
            so.inter_op_num_threads = 1
            self.model = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", quantization="int8", sess_options=so,
                                             providers=["CPUExecutionProvider"])
        elif backend in WHISPER_REPO:
            from faster_whisper import WhisperModel
            self.model = WhisperModel(WHISPER_REPO[backend], device="cpu", compute_type="int8", cpu_threads=threads,
                                      num_workers=1)
        elif backend != "text":
            raise SystemExit(f"unknown backend {backend}")
        self.load_s = time.perf_counter() - t0

    def __call__(self, wav, lang: str) -> str:
        if self.backend == "parakeet":
            return str(self.model.recognize(wav, sample_rate=16000)).strip()
        segs, _info = self.model.transcribe(wav, language=lang, initial_prompt=PROMPT.get(lang, PROMPT["de"]),
                                            beam_size=5, vad_filter=False)
        return " ".join(s.text.strip() for s in segs).strip()


def load_audio(path: Path):
    """16 kHz mono float32; WAV at 16 kHz via soundfile, anything else (phone m4a, 44.1 kHz) decoded with PyAV."""
    import numpy as np
    if path.suffix == ".wav":
        import soundfile as sf
        wav, sr = sf.read(str(path), dtype="float32")
        if sr == 16000:
            return wav.mean(axis=1).astype(np.float32) if wav.ndim > 1 else wav
    import av
    with av.open(str(path)) as c:
        rs = av.AudioResampler(format="flt", layout="mono", rate=16000)
        chunks = [f.to_ndarray().reshape(-1) for fr in c.decode(audio=0) for f in rs.resample(fr)]
        chunks += [f.to_ndarray().reshape(-1) for f in rs.resample(None)]
    return np.concatenate(chunks).astype(np.float32)


# ---------------------------------------------------------------- scoring (logic copied from eval/run_eval.py)
def score(it: dict, text: str, directory) -> dict:
    from engine import request_job
    from engine._core import norm_tokens

    g = it["gold"]
    t0 = time.perf_counter()
    try:
        res = request_job.run(text, directory, use_llm=False)
        err = None
    except Exception as e:  # a garbled transcript must not kill the run
        res, err = None, f"{type(e).__name__}: {e}"[:200]
    eng_ms = (time.perf_counter() - t0) * 1000
    if res is None:
        ok = {k: False for k in ("recipient", "contact", "patient", "doc_type", "ready")}
        return {"ok": ok, "full": False, "silent_error": False, "wrong_patient": False, "engine_ms": eng_ms,
                "engine_error": err, "got": None}
    picked = res["patient"]["ref"] if res["patient"]["status"] in ("unique", "explicit") else None
    ok = {
        "recipient": bool(res["recipient"]) and norm_tokens(res["recipient"]) == norm_tokens(g["recipient"]),
        "contact": (res["contact"] is None) if it.get("trap") == "no_contact"
                   else bool(res["contact"]) and res["contact"]["value"] == g["contact"],
        "patient": picked == g["patient_ref"],
        "doc_type": res["doc_type"] == g["doc_type"],
        "ready": res["ready"] == g["ready"],
    }
    required = ok["recipient"] and ok["contact"] and ok["patient"] and ok["doc_type"]
    return {"ok": ok, "full": ok["ready"] and (required if g["ready"] else True),
            "silent_error": res["ready"] and not required,
            "wrong_patient": picked is not None and picked != g["patient_ref"],
            "engine_ms": eng_ms, "engine_error": None,
            "got": {"recipient": res["recipient"], "contact": (res["contact"] or {}).get("value"), "patient": picked,
                    "doc_type": res["doc_type"], "ready": res["ready"], "missing": res.get("missing")}}


def summarise(per: list[dict]) -> dict:
    n = len(per)
    out = {"n": n,
           "wer_mean": sum(p["wer"] for p in per) / n if n else None,
           "wer_corpus": (sum(p["wer_err"] for p in per) / max(1, sum(p["wer_ref"] for p in per))) if n else None,
           "full_request": rate(sum(p["full"] for p in per), n),
           "fields": {f: rate(sum(p["ok"][f] for p in per), n) for f in ("recipient", "contact", "patient", "doc_type", "ready")},
           "wrong_patient": rate(sum(p["wrong_patient"] for p in per), n, exact=True),
           "silent_error": rate(sum(p["silent_error"] for p in per), n, exact=True),
           "asr_ms_p50": pct([p["asr_ms"] for p in per], 0.5), "asr_ms_p95": pct([p["asr_ms"] for p in per], 0.95),
           "rtf_p50": pct([p["rtf"] for p in per if p["rtf"] is not None], 0.5),
           "by_lang": {}}
    for lang in sorted({p["lang"] for p in per}):
        g = [p for p in per if p["lang"] == lang]
        out["by_lang"][lang] = {"n": len(g), "wer_mean": sum(p["wer"] for p in g) / len(g),
                                "full_request": rate(sum(p["full"] for p in g), len(g)),
                                "contact": rate(sum(p["ok"]["contact"] for p in g), len(g))}
    return out


def run(a) -> None:
    from engine.patients import MemoryDirectory
    from eval.tts import dictated_items

    items = dictated_items(a.set, 80 if a.set == "dev" else None)
    if a.limit:
        items = items[: a.limit]
    directory = MemoryDirectory(json.load(open(DATA / "patients.json", encoding="utf-8")))
    tag = a.set if a.audio == a.set else f"{a.set}-{a.audio}"
    label = a.backend + ("+clean" if a.clean else "")
    out_path = RESULTS / f"voice_{tag}_{label}.json"
    src_path = RESULTS / f"voice_{tag}_{a.backend}.json"
    RESULTS.mkdir(parents=True, exist_ok=True)
    cached = {}
    if (a.reuse or a.clean) and src_path.exists():
        cached = {p["id"]: p for p in json.loads(src_path.read_text(encoding="utf-8"))["items"]}
    need_asr = a.backend != "text" and any(it["id"] not in cached for it in items)
    asr = Asr(a.backend, a.threads) if need_asr else None
    audio_dir = DATA / "audio" / a.audio
    per, t_run = [], time.perf_counter()

    def dump(complete: bool) -> None:
        res = {"set": a.set, "audio": a.audio, "backend": label,
               "model": BACKENDS[a.backend] + (" + punctuation cleanup before the request job" if a.clean else ""), "threads": a.threads,
               "load_s": asr.load_s if asr else None, "complete": complete, "limit": a.limit,
               "wall_s": time.perf_counter() - t_run, "summary": summarise(per), "items": per}
        out_path.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    for i, it in enumerate(items, 1):
        audio_s, asr_ms = None, 0.0
        if a.backend == "text":
            hyp = it["text"]
        elif it["id"] in cached:
            c = cached[it["id"]]
            hyp, asr_ms, audio_s = c["hyp"], c["asr_ms"], c["audio_s"]
        else:
            found = [audio_dir / f"{it['id']}{ext}" for ext in (".wav", ".m4a", ".mp3", ".ogg", ".flac")]
            found = [f for f in found if f.exists()]
            if not found:
                if a.audio == a.set:
                    print(f"missing audio for {it['id']}, skipped")
                continue
            wav = load_audio(found[0])
            audio_s = len(wav) / 16000
            t0 = time.perf_counter()
            hyp = asr(wav, it.get("lang", "de"))
            asr_ms = (time.perf_counter() - t0) * 1000
        if a.clean:
            hyp = clean(hyp)
        e, nref = wer(it["text"], hyp)
        s = score(it, hyp, directory)
        per.append({"id": it["id"], "lang": it.get("lang"), "trap": it.get("trap", "none"), "ref": it["text"], "hyp": hyp,
                    "wer": e / max(1, nref), "wer_err": e, "wer_ref": nref, "asr_ms": asr_ms, "audio_s": audio_s,
                    "rtf": (asr_ms / 1000 / audio_s) if audio_s else None, "gold": it["gold"], **s})
        if i % 10 == 0:
            dump(False)
            sm = summarise(per)
            print(f"  {i}/{len(items)} full={sm['full_request']['p']:.2f} wer={sm['wer_mean']:.3f} "
                  f"asr_p50={sm['asr_ms_p50']:.0f}ms", flush=True)
    dump(True)
    sm = summarise(per)
    print(f"{a.set}/{a.backend}: n={sm['n']} WER={sm['wer_mean']:.3f} full={sm['full_request']['p']:.3f} "
          f"contact={sm['fields']['contact']['p']:.3f} patient={sm['fields']['patient']['p']:.3f} "
          f"wrong_patient={sm['wrong_patient']['k']} silent={sm['silent_error']['k']} -> {out_path}")


# ---------------------------------------------------------------- report
def _r(x: dict) -> str:
    return f"{100 * x['p']:.1f}% [{100 * x['lo']:.0f}–{100 * x['hi']:.0f}]" if x and x["p"] is not None else "–"


def _row(name: str, sm: dict) -> str:
    rtf = f"{sm['rtf_p50']:.2f}" if sm.get("rtf_p50") is not None else "–"
    lat = f"{sm['asr_ms_p50'] / 1000:.1f} s" if sm.get("asr_ms_p50") else "–"
    return (f"| {name} | {sm['n']} | {100 * sm['wer_mean']:.1f}% | {_r(sm['full_request'])} | "
            f"{100 * sm['fields']['contact']['p']:.1f}% | {100 * sm['fields']['patient']['p']:.1f}% | "
            f"{sm['wrong_patient']['k']} | {sm['silent_error']['k']} | {lat} | {rtf} |")


HEADER = ("| backend | n | WER (mean) | full request correct [95% Wilson] | contact exact | patient correct | "
          "wrong patient | silent errors | ASR latency p50 | RTF p50 |\n|---|---|---|---|---|---|---|---|---|---|")


def report() -> None:
    from engine.patients import MemoryDirectory
    from eval.tts import dictated_items

    lines = ["# Voice evaluation (CPU, synthetic dictation)", "",
             "Generated by `python -m eval.voice_eval report` from `eval/results/voice_<set>_<backend>.json`.", "",
             "**Pipeline.** Dictated request items (`style == \"dictated\"`) -> Piper TTS (`piper-tts`, voices "
             "`de_DE-thorsten-medium` / `en_US-lessac-medium` from `rhasspy/piper-voices`, resampled to 16 kHz mono) -> "
             "CPU ASR -> `request_job.run(transcript, MemoryDirectory(patients.json), use_llm=False)` (rules only) -> "
             "same scoring as `eval/run_eval.py`. Row `text` runs the request job on the item's own text (perfect ASR), "
             "so the gap to it is what ASR costs.", "",
             "**Caveats.** One synthetic voice per language, clean audio, no noise, no accents: this is a best case for "
             "ASR, not a field estimate (see `eval/data/voice_script_*.md` for recording real voices). "
             "Timings are on a shared Windows laptop CPU with every model limited to 3 threads while another benchmark "
             "(llama.cpp, ~8 threads) was running -- latency/RTF are inflated and only comparable within this run. "
             "WER is against the dictated wording (\"punkt\", spelled digits), so an ASR that writes `0660…` or "
             "`a.b@c.example` pays WER for a correct hearing; contact exact is the number that matters.", ""]
    # a hand-written findings block between these markers survives regeneration
    md = ROOT / "eval" / "VOICE.md"
    old = md.read_text(encoding="utf-8") if md.exists() else ""
    m = re.search(r"<!-- findings -->.*?<!-- /findings -->", old, re.S)
    lines += [m.group(0) if m else "<!-- findings -->\n<!-- /findings -->", ""]
    files = sorted(RESULTS.glob("voice_*.json"))
    runs: dict[str, dict[str, dict]] = {}
    for f in files:
        r = json.loads(f.read_text(encoding="utf-8"))
        key = r["set"] if r.get("audio", r["set"]) == r["set"] else f"{r['set']}-{r['audio']}"
        runs.setdefault(key, {})[r["backend"]] = r
    directory = MemoryDirectory(json.load(open(DATA / "patients.json", encoding="utf-8")))
    order = ["text", "parakeet", "parakeet+clean", "whisper-small", "whisper-small+clean", "whisper-turbo-de",
             "whisper-turbo-de+clean"]
    for set_name, by in runs.items():
        base = set_name.split("-")[0]
        items = {it["id"]: it for it in dictated_items(base, 80 if base == "dev" else None)}
        lines += [f"## Set `{set_name}`", ""]
        # text baseline on exactly the ids each backend saw
        text_cache: dict[str, dict] = {}

        def text_per(ids: list[str]) -> list[dict]:
            out = []
            for i in ids:
                if i not in text_cache:
                    it = items[i]
                    text_cache[i] = {"id": i, "lang": it["lang"], "wer": 0.0, "wer_err": 0, "wer_ref": len(words(it["text"])),
                                     "asr_ms": 0, "rtf": None, **score(it, it["text"], directory)}
                out.append(text_cache[i])
            return out

        lines += ["### Each backend on the clips it transcribed, with the perfect-ASR row on the same ids", "", HEADER]
        last_ids = None
        for b in order:
            if b == "text" or b not in by:
                continue
            r = by[b]
            ids = [p["id"] for p in r["items"]]
            part = "" if r.get("complete") else " (partial run)"
            if ids != last_ids:
                lines.append(_row(f"text (perfect ASR), same {len(ids)} ids", summarise(text_per(ids))))
            last_ids = ids
            lines.append(_row(f"**{b}**{part}", r["summary"]))
        lines += [""]
        asr_runs = [b for b in order if b in by and b != "text"]
        if len(asr_runs) > 1:
            common = set.intersection(*[{p["id"] for p in by[b]["items"]} for b in asr_runs])
            lines += [f"### Head-to-head on the {len(common)} clips every backend transcribed", "", HEADER,
                      _row("text (perfect ASR)", summarise(text_per(sorted(common))))]
            for b in asr_runs:
                lines.append(_row(b, summarise([p for p in by[b]["items"] if p["id"] in common])))
            lines += ["", "By language (same common clips): full request correct / contact exact / WER", "",
                      "| backend | " + " | ".join(sorted({items[i]["lang"] for i in common})) + " |",
                      "|---|" + "---|" * len({items[i]["lang"] for i in common})]
            langs = sorted({items[i]["lang"] for i in common})
            for b, per in [("text", text_per(sorted(common)))] + [(b, [p for p in by[b]["items"] if p["id"] in common]) for b in asr_runs]:
                cells = []
                for lg in langs:
                    g = [p for p in per if p["lang"] == lg]
                    cells.append(f"n={len(g)}: {100 * sum(p['full'] for p in g) / len(g):.0f}% / "
                                 f"{100 * sum(p['ok']['contact'] for p in g) / len(g):.0f}% / {100 * sum(p['wer'] for p in g) / len(g):.1f}%")
                lines.append(f"| {b} | " + " | ".join(cells) + " |")
            lines += [""]
        if asr_runs:
            lines += ["### Where ASR breaks the request (vs the perfect transcript of the same clip)", "",
                      "Counts of clips where the field is right on the item text but wrong on the transcript "
                      "(\"gained\" = wrong on text, right on transcript, e.g. ASR capitalises a name the rules then find).", "",
                      "| backend | n | contact lost: e-mail -> none / wrong | contact lost: phone -> none / wrong | "
                      "recipient lost / gained | patient lost / gained | doc type lost | full lost / gained |",
                      "|---|---|---|---|---|---|---|---|"]
            for b in asr_runs:
                per = by[b]["items"]
                cnt = {k: 0 for k in ("em_none", "em_wrong", "ph_none", "ph_wrong", "rec_l", "rec_g", "pat_l", "pat_g",
                                      "doc_l", "full_l", "full_g")}
                for p in per:
                    t = text_per([p["id"]])[0]
                    if t["ok"]["contact"] and not p["ok"]["contact"] and p["gold"]["contact"]:
                        none = not (p.get("got") or {}).get("contact")
                        kind = "em" if p["gold"]["contact_kind"] == "email" else "ph"
                        cnt[f"{kind}_{'none' if none else 'wrong'}"] += 1
                    for f, k in (("recipient", "rec"), ("patient", "pat")):
                        cnt[f"{k}_l"] += t["ok"][f] and not p["ok"][f]
                        cnt[f"{k}_g"] += p["ok"][f] and not t["ok"][f]
                    cnt["doc_l"] += t["ok"]["doc_type"] and not p["ok"]["doc_type"]
                    cnt["full_l"] += t["full"] and not p["full"]
                    cnt["full_g"] += p["full"] and not t["full"]
                lines.append(f"| {b} | {len(per)} | {cnt['em_none']} / {cnt['em_wrong']} | {cnt['ph_none']} / {cnt['ph_wrong']} | "
                             f"{cnt['rec_l']} / {cnt['rec_g']} | {cnt['pat_l']} / {cnt['pat_g']} | {cnt['doc_l']} | "
                             f"{cnt['full_l']} / {cnt['full_g']} |")
            lines += [""]
        for b in asr_runs:
            r = by[b]
            fails =[p for p in r["items"] if not p["full"] and text_per([p["id"]])[0]["full"]]
            lines += [f"### `{b}`: requests lost to ASR ({len(fails)} of {len(r['items'])} clips fail although the "
                      f"perfect transcript passes) -- first 5", "", f"Model: {r['model']}; load {r.get('load_s') or 0:.0f} s; "
                      f"wall {r.get('wall_s', 0) / 60:.1f} min.", ""]
            for p in fails[:5]:
                bad = [k for k, v in p["ok"].items() if not v]
                got = p.get("got") or {}
                lines += [f"- `{p['id']}` ({p['lang']}, trap {p['trap']}) failed: {', '.join(bad) or 'ready'}; "
                          f"contact got `{got.get('contact')}` vs gold `{p['gold']['contact']}`; recipient got "
                          f"`{got.get('recipient')}` vs `{p['gold']['recipient']}`",
                          f"  - said: {p['ref']}", f"  - heard: {p['hyp']}"]
            lines += [""]
    lines += ["## Reproduce", "", "```bash",
              "export UV_PROJECT_ENVIRONMENT=C:/Users/medya/.venvs/befundbruecke PYTHONIOENCODING=utf-8",
              "uv sync --group voice   # piper-tts, onnx-asr, faster-whisper, soundfile",
              "uv run --no-sync python -m eval.tts --set test",
              "uv run --no-sync python -m eval.voice_eval run --set test --backend text",
              "uv run --no-sync python -m eval.voice_eval run --set test --backend parakeet",
              "uv run --no-sync python -m eval.voice_eval run --set test --backend whisper-small",
              "uv run --no-sync python -m eval.voice_eval run --set test --backend whisper-turbo-de --limit 60",
              "uv run --no-sync python -m eval.voice_eval report", "```",
              "", "`--reuse` re-scores cached transcripts without running ASR again (e.g. after an engine change).", ""]
    (ROOT / "eval" / "VOICE.md").write_text("\n".join(lines), encoding="utf-8")
    print("wrote eval/VOICE.md")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--set", default="test", choices=["test", "dev"])
    r.add_argument("--backend", required=True, choices=list(BACKENDS))
    r.add_argument("--limit", type=int, default=None)
    r.add_argument("--threads", type=int, default=3)
    r.add_argument("--audio", default=None, help="audio folder under eval/data/audio (default: --set; 'human' for phone "
                   "recordings named <id>.m4a/.wav)")
    r.add_argument("--clean", action="store_true", help="re-score the backend's cached transcripts after clean() -> "
                   "voice_<set>_<backend>+clean.json")
    r.add_argument("--reuse", action="store_true", help="reuse transcripts from an earlier run's JSON")
    sub.add_parser("report")
    a = ap.parse_args()
    if a.cmd == "run" and not a.audio:
        a.audio = a.set
    run(a) if a.cmd == "run" else report()


if __name__ == "__main__":
    main()
