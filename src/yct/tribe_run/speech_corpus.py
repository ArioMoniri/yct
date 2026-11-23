"""D-085 draft: the SPK / BURST / TALKFACE speech corpus (owner-approved spec, 2026-11-22).

- Source: the IEEE/Harvard sentences (IEEE Recommended Practice for Speech Quality Measurements, 1969,
  Appendix C), 72 lists x 10, parsed in list order from the recorded source page.
- Public/private split (owner 2026-11-22): the committed corpus file holds only (list, item, sha256) plus the
  raw page sha256; no sentence text is ever committed. The raw page lives in the private yct bucket
  (speech.private_raw_s3); resolve_texts() re-parses it at build time and checks the raw sha and every item
  sha (fail closed). Selection logs with text stay private; public_record() strips text for the repo.
- Exclusion: a frozen lexicon file (exact lowercase tokens by category) plus two rules (proper noun = a
  capitalised non-initial token other than "I"; number = a digit or a number word). A sentence that hits
  any rule is excluded with its reasons; nobody edits a sentence.
- Order: ascending sha256(text) over the kept sentences (the queue).
- Selection (at synthesis time, only after speech_corpus_sha256 is frozen): families are filled in
  fill_order; each slot pops the next queue item(s) (SPK: the leading 3 words, owner 2026-11-22; BURST: two
  sentences as one text; TALKFACE: one sentence), synthesises it, and keeps it iff its -40 dBFS speech span
  lies inside the family range. A failure is logged and the next queue item takes the same slot. Exhaustion
  is a STOP to the owner. Nobody listens to choose items.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

KEY = "controls.refclips_artifacts.speech_corpus_sha256"


class CorpusStopError(RuntimeError):
    """Fail-closed STOP to the owner (queue exhausted, or a private text that does not match its sha).
    On queue exhaustion `partial` holds the selection state so far (counts, kept/rejected records)."""

    partial: dict | None = None


def parse_harvard_html(text: str) -> list[dict[str, Any]]:
    """Rows {list, item, text} in source order: each <h2>List N</h2> followed by its <li> items."""
    out: list[dict[str, Any]] = []
    for m in re.finditer(r"<h2>\s*List\s+(\d+)\s*</h2>(.*?)(?=<h2>|\Z)", text, re.S | re.I):
        items = re.findall(r"<li>(.*?)</li>", m.group(2), re.S | re.I)
        for j, it in enumerate(items, 1):
            s = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", it))).strip()
            out.append({"list": int(m.group(1)), "item": j, "text": s})
    return out


def tokens(text: str) -> list[str]:
    raw = [t for w in text.split() for t in w.split("-")]
    return [t.strip(".,;:!?\"'()") for t in raw if t.strip(".,;:!?\"'()")]


def exclusion_reasons(text: str, lexicon: dict) -> list[str]:
    """lexicon = the lexicon file's `categories` (or the whole file, which carries `categories` and
    `number_words`). Returns the sorted reasons (empty = kept)."""
    cats = lexicon.get("categories", lexicon)
    numw = set(lexicon.get("number_words", ())) or {
        "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "hundred", "thousand"}
    toks = tokens(text)
    low = [t.lower() for t in toks]
    why = set()
    if any(t[:1].isupper() and t != "I" for t in toks[1:]):
        why.add("proper_noun")
    if any(any(ch.isdigit() for ch in t) or t in numw for t in low):
        why.add("number")
    for cat, words in cats.items():
        if set(low) & set(words):
            why.add(cat)
    return sorted(why)


def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_corpus(rows: list[dict], lexicon: dict, spec: dict, source: dict) -> dict[str, Any]:
    kept, excluded = [], []
    for r in rows:
        why = exclusion_reasons(r["text"], lexicon)
        rec = {"list": r["list"], "item": r["item"], "sha256": sha_text(r["text"])}
        (excluded.append({**rec, "reasons": why}) if why else kept.append(rec))
    kept.sort(key=lambda r: r["sha256"])
    return {"version": "speech_corpus_v1", "decision": "D-085 draft",
            "source": {**source, "n_sentences": len(rows)},
            "lexicon_sha256": lexicon.get("_sha256"),
            "synthesis": {k: spec[k] for k in ("engine", "voice", "rate_wpm", "pitch", "amplitude")},
            "rules": {k: spec[k] for k in ("order", "span_dbfs", "counts", "ranges_s", "spk_words",
                                           "burst_sentences", "fill_order", "on_exhausted")},
            "licence_status": spec["licence_status"],
            "queue": kept, "excluded": excluded}


def resolve_texts(doc: dict, raw: bytes) -> list[dict[str, Any]]:
    """The corpus queue with texts, from the private raw page. STOP unless sha256(raw) equals the recorded
    raw_sha256 and every queue item's (list, item) text hashes to its recorded sha256."""
    if hashlib.sha256(raw).hexdigest() != doc["source"]["raw_sha256"]:
        raise CorpusStopError("private raw page sha256 does not match the corpus raw_sha256 (STOP)")
    by_id = {(r["list"], r["item"]): r["text"] for r in parse_harvard_html(raw.decode("utf-8"))}
    out = []
    for q in doc["queue"]:
        key = (q["list"], q["item"])
        if key not in by_id:
            raise CorpusStopError(f"queue item {key} not in the source page (STOP)")
        if sha_text(by_id[key]) != q["sha256"]:
            raise CorpusStopError(f"queue item {key} text sha256 mismatch (STOP)")
        out.append({**q, "text": by_id[key]})
    return out


def public_record(obj: Any) -> Any:
    """A copy with every `text` field removed, for anything that is committed to the public repo."""
    if isinstance(obj, dict):
        return {k: public_record(v) for k, v in obj.items() if k != "text"}
    if isinstance(obj, list):
        return [public_record(v) for v in obj]
    return obj


def spk_words(i: int, k: int, n: int = 3) -> int:
    """SPK clip i, event k: owner 2026-11-22, 3-word leads only at 175 wpm (a 2-word span, ~0.69 s, can never
    reach the 1.0 s floor). The design_v2 2/3 balance is dropped and disclosed."""
    return n


def speech_span(x: np.ndarray, sr: int, dbfs: float) -> tuple[int, int]:
    """[s0, s1): first to one-past-last sample with |x| >= 10^(dbfs/20) (x in full-scale units)."""
    thr = 10 ** (dbfs / 20)
    idx = np.flatnonzero(np.abs(np.asarray(x, np.float64)) >= thr)
    if idx.size == 0:
        raise ValueError("synthesised item is silent at the span threshold")
    return int(idx[0]), int(idx[-1]) + 1


Synth = Callable[..., tuple[np.ndarray, int]]   # synth(text) or, under D-089, synth(text, rate_wpm=...)


def effective_spec(cfg: dict) -> dict:
    """The frozen D-085 part-2 speech key with the D-089 per-family rates layered on (the frozen key itself
    is never edited). Without a refclips_d089 block this is the frozen key unchanged."""
    base = cfg["controls"]["refclips_d085"]["speech"]
    d089 = cfg["controls"].get("refclips_d089")
    if not d089:
        return base
    return {**base, "rate_wpm_by_family": dict(d089["rate_wpm_by_family"])}


def expected_spk_at_rate(spans: list[float], rate_from: int, rate_to: int, rng: tuple[float, float]) -> dict:
    """D-089 a-priori estimate, numbers only: scale recorded spans linearly by rate_from / rate_to and count
    how many fall inside the SPK range (an approximation: espeak pauses do not scale exactly linearly)."""
    lo, hi = rng
    sc = [x * rate_from / rate_to for x in spans]
    n = len(sc)
    ok = sum(lo <= x <= hi for x in sc)
    srt = sorted(sc)
    return {"n": n, "pass": ok, "too_short": sum(x < lo for x in sc), "too_long": sum(x > hi for x in sc),
            "rate": ok / n, "median_s": srt[n // 2], "min_s": srt[0], "max_s": srt[-1]}


def select(queue: list[dict], synth: Synth, spec: dict) -> dict[str, Any]:
    if not getattr(synth, "verified", None):     # watchdog: only a pin-verified engine (EspeakSynth) selects
        raise SystemExit("select needs a pin-verified synth (no .verified): STOP")
    pos = 0
    items: dict[str, list[dict]] = {f: [] for f in spec["fill_order"]}
    rejects: list[dict] = []
    rates = {f: {"tried": 0, "kept": 0} for f in spec["fill_order"]}
    n_spk = int(spec.get("spk_words", 3))
    by_fam = spec.get("rate_wpm_by_family")       # D-089: per-family rate; absent -> synth(text) as frozen
    cur = {"family": None, "slot": None}

    def pop(n: int) -> list[dict]:
        nonlocal pos
        if pos + n > len(queue):
            err = CorpusStopError(f"speech corpus queue exhausted at position {pos} (STOP to the owner)")
            err.partial = {"items": items, "rejects": rejects, "queue_used": pos, "pass_rates": rates,
                           "family": cur["family"], "slot": cur["slot"]}
            raise err
        got = queue[pos:pos + n]
        pos += n
        return got

    for fam in spec["fill_order"]:
        lo, hi = spec["ranges_s"][fam]
        for u in range(spec["counts"][fam]):
            cur.update(family=fam, slot=u)
            while True:
                if fam == "SPK":
                    src = pop(1)
                    nw = spk_words(u // 3, u % 3, n_spk)
                    text = " ".join(tokens(src[0]["text"])[:nw])
                elif fam == "BURST":
                    src = pop(spec["burst_sentences"])
                    nw = None
                    text = " ".join(s["text"] for s in src)
                else:
                    src = pop(1)
                    nw = None
                    text = src[0]["text"]
                x, sr = synth(text, rate_wpm=by_fam[fam]) if by_fam else synth(text)
                s0, s1 = speech_span(x, sr, spec["span_dbfs"])
                d = (s1 - s0) / sr
                rec = {"slot": u, "text": text, "n_words": nw, "span_s": round(d, 4),
                       "source_sha256": [s["sha256"] for s in src]}
                rates[fam]["tried"] += 1
                if lo <= d <= hi:
                    items[fam].append(rec)
                    rates[fam]["kept"] += 1
                    break
                rejects.append({**rec, "family": fam, "reason": "duration"})
    out = {"items": items, "rejects": rejects, "queue_used": pos, "pass_rates": rates}
    if by_fam:
        out["rate_wpm_by_family"] = dict(by_fam)
    return out


def require_frozen(cfg: dict) -> None:
    if not any(f.get("key") == KEY for f in cfg.get("frozen", [])):
        raise SystemExit(f"{KEY} is not frozen: no synthesis before the corpus freeze (D-085)")


def _frozen(cfg: dict, key: str) -> bool:
    """A key is frozen if it, or an ancestor of it, has a frozen: row."""
    return any(key == f.get("key") or key.startswith(f.get("key", "") + ".") for f in cfg.get("frozen", []))


def speech_build_preconditions(cfg: dict) -> None:
    """Council D-085 (c): no SPK / BURST / TALKFACE build before the speech and TALKFACE keys, the corpus sha
    and the T-ENV code are all frozen (T-ENV set: module + blob sha1)."""
    d = cfg["controls"]["refclips_d085"]
    miss = [k for k in d["speech"]["requires_frozen_before_build"] if not _frozen(cfg, k)]
    if not d["tenv"]["module"] or not d["tenv"]["blob_sha1"]:
        miss.append("controls.refclips_d085.tenv (module / blob_sha1 unset)")
    if miss:
        raise SystemExit(f"speech build refused, not frozen: {miss} (D-085)")


def corpus_sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_corpus(doc: dict, path: Path) -> str:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    return corpus_sha(path)
