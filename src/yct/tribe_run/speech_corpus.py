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
  fill_order; each slot pops the next queue item(s) (SPK: the leading 2 or 3 words by spk_words; BURST: two
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
    """Fail-closed STOP to the owner (queue exhausted, or a private text that does not match its sha)."""


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
            "rules": {k: spec[k] for k in ("order", "span_dbfs", "counts", "ranges_s", "spk_words_rule",
                                           "burst_sentences", "fill_order", "on_exhausted")},
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


def spk_words(i: int, k: int) -> int:
    """SPK clip i, event k (utterance 3i + k): 15/15 two/three-word items within each half (i % 2)."""
    return 2 if (k + i // 2) % 2 == 0 else 3


def speech_span(x: np.ndarray, sr: int, dbfs: float) -> tuple[int, int]:
    """[s0, s1): first to one-past-last sample with |x| >= 10^(dbfs/20) (x in full-scale units)."""
    thr = 10 ** (dbfs / 20)
    idx = np.flatnonzero(np.abs(np.asarray(x, np.float64)) >= thr)
    if idx.size == 0:
        raise ValueError("synthesised item is silent at the span threshold")
    return int(idx[0]), int(idx[-1]) + 1


Synth = Callable[[str], tuple[np.ndarray, int]]


def select(queue: list[dict], synth: Synth, spec: dict) -> dict[str, Any]:
    pos = 0
    items: dict[str, list[dict]] = {f: [] for f in spec["fill_order"]}
    rejects: list[dict] = []

    def pop(n: int) -> list[dict]:
        nonlocal pos
        if pos + n > len(queue):
            raise CorpusStopError(f"speech corpus queue exhausted at position {pos} (STOP to the owner)")
        got = queue[pos:pos + n]
        pos += n
        return got

    for fam in spec["fill_order"]:
        lo, hi = spec["ranges_s"][fam]
        for u in range(spec["counts"][fam]):
            while True:
                if fam == "SPK":
                    src = pop(1)
                    nw = spk_words(u // 3, u % 3)
                    text = " ".join(tokens(src[0]["text"])[:nw])
                elif fam == "BURST":
                    src = pop(spec["burst_sentences"])
                    nw = None
                    text = " ".join(s["text"] for s in src)
                else:
                    src = pop(1)
                    nw = None
                    text = src[0]["text"]
                x, sr = synth(text)
                s0, s1 = speech_span(x, sr, spec["span_dbfs"])
                d = (s1 - s0) / sr
                rec = {"slot": u, "text": text, "n_words": nw, "span_s": round(d, 4),
                       "source_sha256": [s["sha256"] for s in src]}
                if lo <= d <= hi:
                    items[fam].append(rec)
                    break
                rejects.append({**rec, "family": fam, "reason": "duration"})
    return {"items": items, "rejects": rejects, "queue_used": pos}


def require_frozen(cfg: dict) -> None:
    if not any(f.get("key") == KEY for f in cfg.get("frozen", [])):
        raise SystemExit(f"{KEY} is not frozen: no synthesis before the corpus freeze (D-085)")


def corpus_sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_corpus(doc: dict, path: Path) -> str:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    return corpus_sha(path)
