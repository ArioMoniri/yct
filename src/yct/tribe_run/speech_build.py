"""D-085 part 2 step 4 (D-089 rates): build-side helpers for the SPK / BURST speech clips and their QC.

- check_selection_record: the frozen public selection record (D-089 rates) must have its sha frozen and equal
  to the committed file; D-089 itself must be frozen.
- reconstruct_texts: texts never come from git. They are rebuilt from the resolved private queue (every text
  sha checked by speech_corpus.resolve_texts) with the frozen selection rules, keyed by each item's
  source_sha256: SPK = the leading spk_words tokens of one source; BURST = burst_sentences sources joined
  with one space; TALKFACE = one source. Slots must be 0..n-1 in order. Any mismatch is a STOP.
- utterance_map: every planned event (clip, k) -> (family, selection slot); refclips58.plan uses utterance
  3*i + k for SPK / BURST and k for TALKFACE.
- speech_rows: the frozen QC per SPK / BURST clip on the RENDERED 48 kHz int16 audio: the constructive
  speech gate (refclips_qc85.speech_gate, gating) and, for SPK, the integer span QC
  (refclips_qc85.spk_span_qc, gating, D-089 build_qc tolerance). The utterances are re-synthesised by
  the provider (an independent second synthesis), so the gate also checks engine determinism. T-ENV
  envelope numbers are descriptive only.
- assert_no_text: nothing written for the public repo may contain a selected text (fail closed).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from yct.tribe_run import refclips58 as R  # noqa: N812
from yct.tribe_run import refclips_qc85 as Q  # noqa: N812
from yct.tribe_run import speech_corpus as S  # noqa: N812

SEL_KEY = "controls.refclips_artifacts.speech_selection_sha256"
SEL_PATH = "outputs/runs/d089_selection/speech_selection_d089.json"
BUILD_FAMILIES = ("GREY_CTRL", "SPK", "BURST")
CTRL = "grey_ctrl_00"


def _frozen(cfg: dict, key: str) -> bool:
    return any(f.get("key") == key for f in cfg.get("frozen", []))


def require_d089(cfg: dict) -> None:
    if not _frozen(cfg, "controls.refclips_d089"):
        raise SystemExit("controls.refclips_d089 is not frozen: no D-089 speech build (STOP)")


def check_selection_record(cfg: dict, root: Path) -> dict:
    if not _frozen(cfg, SEL_KEY):
        raise SystemExit(f"{SEL_KEY} is not frozen: no speech build before the selection freeze")
    p = Path(root) / SEL_PATH
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    if sha != cfg["controls"]["refclips_artifacts"]["speech_selection_sha256"]:
        raise SystemExit(f"selection record sha256 {sha[:12]} != the frozen speech_selection_sha256 (STOP)")
    return json.loads(p.read_text())


def reconstruct_texts(sel: dict, queue: list[dict], spk_words: int = 3, burst_sentences: int = 2) -> dict:
    by_sha = {q["sha256"]: q["text"] for q in queue}
    n_src = {"SPK": 1, "BURST": burst_sentences, "TALKFACE": 1}
    out = {**sel, "items": {}}
    for fam, rows in sel["items"].items():
        new = []
        for j, it in enumerate(rows):
            if it.get("slot") != j:
                raise SystemExit(f"{fam}: slot {it.get('slot')} at position {j} (slots must be 0..n-1): STOP")
            src = list(it["source_sha256"])
            if len(src) != n_src[fam]:
                raise SystemExit(f"{fam} slot {j}: {len(src)} sources != {n_src[fam]}: STOP")
            miss = [s for s in src if s not in by_sha]
            if miss:
                raise SystemExit(f"{fam} slot {j}: source {miss[0][:12]} not in the resolved queue: STOP")
            if fam == "SPK":
                if it.get("n_words") != spk_words:
                    raise SystemExit(f"SPK slot {j}: n_words {it.get('n_words')} != {spk_words}: STOP")
                text = " ".join(S.tokens(by_sha[src[0]])[:spk_words])
            else:
                text = " ".join(by_sha[s] for s in src)
            new.append({**it, "text": text})
        out["items"][fam] = new
    return out


def utterance_map(clips: list, sel: dict) -> dict[tuple[str, int], tuple[str, int]]:
    out = {}
    for c in clips:
        rows = sel["items"].get(c.family, [])
        for e in c.events:
            idx = int(e["utterance"])
            if idx >= len(rows) or rows[idx].get("slot") != idx:
                raise SystemExit(f"{c.name} event {e['k']}: utterance {idx} has no selection slot: STOP")
            out[(c.name, int(e["k"]))] = (c.family, idx)
    return out


def envelope_descriptive(clip, audio48: np.ndarray, sr: int, cfg: dict) -> dict[str, Any]:
    """T-ENV speech_envelope on the clip (16 kHz, band-limited from the rendered 48 kHz): mean envelope in
    utterance TRs over the rest, and the point-biserial r with the utterance indicator. Never gates."""
    from yct.confounds.envelope import SR as SR16
    from yct.confounds.envelope import speech_envelope_per_tr

    tr = float(cfg["tribe"]["tr_s"])
    x16 = R.resample_bandlimited(np.asarray(audio48, np.float64), sr, SR16)
    env = speech_envelope_per_tr(x16, SR16, tr)
    ind = np.zeros(len(env), bool)
    for e in clip.events:
        a, b = e["onset"], e["onset"] + float(e.get("utterance_s", 1.0))
        ind[int(a // tr):min(len(env), int(np.ceil(b / tr)))] = True
    on, off = env[ind], env[~ind]
    ratio = float(on.mean() / off.mean()) if off.size and off.mean() else float("nan")
    r = float(np.corrcoef(env, ind.astype(float))[0, 1]) if env.std() and ind.std() else float("nan")
    return {"event_nonevent_ratio": ratio, "point_biserial_r": r, "n_event_trs": int(ind.sum()),
            "gating": False}


def speech_rows(clips: list, rendered: dict[str, np.ndarray], prov, sel: dict, cfg: dict) -> list[dict]:
    """The frozen speech QC rows for the SPK / BURST clips (GREY_CTRL is the control rendering)."""
    b = cfg["controls"]["refclips_d089"]["build_qc"]
    rng = tuple(cfg["controls"]["refclips_d085"]["speech"]["ranges_s"]["SPK"])
    bed = R.bed()
    rows = []
    for c in clips:
        if c.family not in R.AUDIO:
            continue
        utt = {e["k"]: prov(c.family, int(e["utterance"]))[0] for e in c.events}
        for e in c.events:
            e.setdefault("utterance_s", len(utt[e["k"]]) / R.SR)
        place = [(e["onset"], utt[e["k"]]) for e in c.events]
        ck: dict[str, Any] = {"speech_gate": Q.speech_gate(rendered[c.name], rendered[CTRL], bed, place)}
        if c.family == "SPK":
            pairs = [(int(sel["items"]["SPK"][int(e["utterance"])]["span_samples"]), utt[e["k"]])
                     for e in c.events]
            ck["spk_span"] = Q.spk_span_qc(pairs, sr=int(b["sr"]), rng=rng,
                                           tol_samples=int(b["spk_span_tol_samples"]),
                                           dbfs=float(b["span_dbfs"]))
        x = np.asarray(rendered[c.name], np.float64) / 32768.0
        ck["envelope"] = envelope_descriptive(c, x, R.SR, cfg)
        r = {"name": c.name, "family": c.family, "checks": ck}
        r["pass"] = Q.row_pass(r)
        rows.append(r)
    return rows


def assert_no_text(obj: Any, sel: dict) -> None:
    blob = json.dumps(obj, default=str)
    for fam, rows in sel["items"].items():
        for it in rows:
            t = it.get("text")
            if t and t in blob:
                raise SystemExit(f"public output contains a {fam} selection text "
                                 f"(slot {it.get('slot')}): STOP")
