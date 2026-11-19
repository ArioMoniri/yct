"""Single loader for P4 prediction locations (D-067 c, QA #2).

Every P4b/P5 reader gets prediction keys from here, never from a fixed path. It applies
config p4.superseded_run_ids, requires exactly one revisions hash across the passing rows,
requires every key under pred_clampv1/, and requires exactly one passing row per job in the
frozen run sets. It returns S3 keys and sha256s only; it never opens an array (D-063 B2).
"""
from __future__ import annotations

import json
from dataclasses import dataclass

PRED_PREFIX = "pred_clampv1/"


@dataclass(frozen=True)
class PredRef:
    video_id: str
    track: str
    run_id: str
    pred_key: str
    pred_sha256: str
    revisions_sha256: str


def _rows(store) -> list[dict]:
    text = store.s3_get_text("manifest.jsonl")
    if text is None:
        raise SystemExit("P4 manifest.jsonl missing")
    return [json.loads(x) for x in text.splitlines() if x.strip()]


def p4_index(store, p4_cfg: dict) -> dict[tuple[str, str], PredRef]:
    sup = set(p4_cfg["superseded_run_ids"])
    want = {("t3", v) for v in p4_cfg["run_set_t3"]} | {("t1", v) for v in p4_cfg["run_set_t1"]}
    keys = set(store.s3_list(PRED_PREFIX))
    passing = [r for r in _rows(store) if r.get("gate_pass") is True and r.get("run_id") not in sup]
    out: dict[tuple[str, str], PredRef] = {}
    for r in passing:
        track, vid = str(r["track"]).lower(), r["video_id"]
        if (track, vid) not in want:
            continue
        if (track, vid) in out:
            raise RuntimeError(f"two passing rows for {track}/{vid}")
        if not r["pred_key"].startswith(PRED_PREFIX):
            raise RuntimeError(f"{track}/{vid} pred_key outside {PRED_PREFIX}: {r['pred_key']}")
        if r["pred_key"] not in keys:
            raise RuntimeError(f"{track}/{vid} pred_key not in store: {r['pred_key']}")
        out[(track, vid)] = PredRef(vid, track, r["run_id"], r["pred_key"], r["pred_sha256"],
                                    r["revisions_sha256"])
    missing = sorted(want - set(out))
    if missing:
        raise RuntimeError(f"{len(missing)} run-set jobs without a passing row: {missing[:5]}")
    revs = {p.revisions_sha256 for p in out.values()}
    if len(revs) != 1:
        raise RuntimeError(f"P4 predictions mix {len(revs)} revisions sets")
    return out
