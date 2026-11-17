"""Content-addressed TRIBE feature cache: determinism by design (BUG-006).

P0 (run smoke_20261117T142354Z) showed that two fresh TRIBE runs differ (max 3.57e-3) because the GPU
feature extractors (fp16 backbones) are nondeterministic, while re-predicting from cached features is
bit-identical. So:

* features are extracted EXACTLY ONCE per input sha256 into ``<root>/<sha256>/`` (``input/`` holds the
  clip copy + transcript, ``feat/`` the extractor's tensors), and a sidecar ``features.meta.json``
  records the sha256 (and shape/dtype for .npy) of every cached file plus the extractor revisions;
* every prediction (reruns, ablations, controls) reads only the cache. The cache is re-hashed before
  and after each prediction; any change, missing or new file raises ``FeatureCacheError`` (so a
  predictor that silently re-extracts cannot go unnoticed);
* fresh-extraction drift (throw-away re-extraction vs the cache) is REPORTED as a metric, never gated.

Extraction and prediction both run inside ``yct.transcribe.asr_guard()`` (no unpinned WhisperX).
The extractor/predictor are callables so the logic is tested on CPU with mocks
(tests/test_tribe_feature_cache.py); ``run_clip.py`` supplies the TRIBE implementations.

    extract(video: Path, feat_dir: Path) -> None          # writes feature files under feat_dir
    predict(video: Path, feat_dir: Path) -> (preds, aux)  # preds: np.ndarray (T, V); aux: anything
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from yct.transcribe import asr_guard

SIDECAR = "features.meta.json"
MARKER = ".extracting"
SIDECAR_SUFFIXES = (".tsv",)  # files copied next to the clip (hand-made / pinned transcript)

Extractor = Callable[[Path, Path], None]
Predictor = Callable[[Path, Path], tuple[np.ndarray, Any]]


class FeatureCacheError(RuntimeError):
    """The cache is incomplete, inconsistent with its sidecar, or was modified by a prediction."""


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _hash_tree(d: Path) -> dict[str, str]:
    if not d.exists():
        return {}
    return {p.relative_to(d).as_posix(): sha256_file(p) for p in sorted(d.rglob("*")) if p.is_file()}


def _tensor_info(p: Path, digest: str) -> dict[str, Any]:
    info: dict[str, Any] = {"sha256": digest, "bytes": p.stat().st_size}
    if p.suffix == ".npy":
        a = np.load(p, mmap_mode="r", allow_pickle=False)
        info.update({"shape": list(a.shape), "dtype": str(a.dtype)})
    return info


def _diff(expected: dict[str, str], actual: dict[str, str], where: str) -> list[str]:
    out = [f"missing {where}/{k}" for k in sorted(set(expected) - set(actual))]
    out += [f"unexpected new file {where}/{k}" for k in sorted(set(actual) - set(expected))]
    out += [f"changed {where}/{k}" for k in sorted(set(expected) & set(actual)) if expected[k] != actual[k]]
    return out


def _sidecars(video: Path) -> list[Path]:
    return [video.with_suffix(s) for s in SIDECAR_SUFFIXES if video.with_suffix(s).exists()]


class FeatureStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser()

    def entry_dir(self, input_sha256: str) -> Path:
        return self.root / input_sha256

    def meta(self, input_sha256: str) -> dict[str, Any] | None:
        e = self.entry_dir(input_sha256)
        if not e.exists():
            return None
        if (e / MARKER).exists() or not (e / SIDECAR).exists():
            raise FeatureCacheError(f"incomplete cache entry {e} (extraction crashed?); inspect, remove")
        return json.loads((e / SIDECAR).read_text())

    def verify(self, input_sha256: str, when: str = "before prediction") -> dict[str, Any]:
        """Re-hash every cached file and compare with the sidecar; raise on any difference."""
        meta = self.meta(input_sha256)
        if meta is None:
            raise FeatureCacheError(f"no cache entry for {input_sha256}")
        e = self.entry_dir(input_sha256)
        problems = _diff({k: v["sha256"] for k, v in meta["tensors"].items()}, _hash_tree(e / "feat"), "feat")
        problems += _diff(meta["input_files"], _hash_tree(e / "input"), "input")
        if problems:
            verb = "prediction step modified feature cache" if when == "after prediction" else "cache corrupt"
            raise FeatureCacheError(f"{verb} ({e}): " + "; ".join(problems))
        return meta

    def ensure(self, video: str | Path, extract: Extractor, revisions: dict[str, Any]
               ) -> tuple[str, dict[str, Any], bool]:
        """Return (input_sha256, meta, reused). Extracts only if no entry exists for the input sha256."""
        video = Path(video)
        sha = sha256_file(video)
        meta = self.meta(sha)
        if meta is not None:
            if meta["revisions"] != revisions:
                raise FeatureCacheError(
                    f"extractor revision mismatch for {sha}: cached {meta['revisions']} vs requested "
                    f"{revisions}; never mix revisions (use a new cache root)")
            for sc in _sidecars(video):
                cached = meta["input_files"].get(Path(meta["input_name"]).with_suffix(sc.suffix).name)
                if cached is not None and cached != sha256_file(sc):
                    raise FeatureCacheError(f"{sc.name} differs from the transcript cached for {sha}")
            return sha, self.verify(sha), True
        e = self.entry_dir(sha)
        (e / "input").mkdir(parents=True)
        (e / MARKER).write_text(json.dumps({"pid": os.getpid(), "t": time.time()}))
        clip = e / "input" / video.name
        shutil.copy2(video, clip)
        for sc in _sidecars(video):
            shutil.copy2(sc, clip.with_suffix(sc.suffix))
        (e / "feat").mkdir()
        with asr_guard():
            extract(clip, e / "feat")
        feat = _hash_tree(e / "feat")
        if not feat:
            raise FeatureCacheError(f"extractor wrote no features for {sha}")
        meta = {
            "input_sha256": sha,
            "input_name": video.name,
            "revisions": revisions,
            "n_extractions": 1,
            "created_t": time.time(),
            "tensors": {k: _tensor_info(e / "feat" / k, v) for k, v in feat.items()},
            "input_files": _hash_tree(e / "input"),
        }
        tmp = e / (SIDECAR + ".tmp")
        tmp.write_text(json.dumps(meta, indent=1, sort_keys=True))
        tmp.replace(e / SIDECAR)
        (e / MARKER).unlink()
        return sha, meta, False


def predict_cached(store: FeatureStore, input_sha256: str, predict: Predictor) -> tuple[np.ndarray, Any]:
    meta = store.verify(input_sha256, "before prediction")
    e = store.entry_dir(input_sha256)
    with asr_guard():
        preds, aux = predict(e / "input" / meta["input_name"], e / "feat")
    store.verify(input_sha256, "after prediction")
    return np.asarray(preds), aux


def _compare(a: np.ndarray, b: np.ndarray) -> dict[str, Any]:
    a64, b64 = np.asarray(a, np.float64).ravel(), np.asarray(b, np.float64).ravel()
    if a64.shape != b64.shape:
        return {"shape_match": False}
    r = float(np.corrcoef(a64, b64)[0, 1]) if a64.size > 1 and a64.std() > 0 and b64.std() > 0 else None
    return {"shape_match": True, "max_abs_diff": float(np.max(np.abs(a64 - b64))) if a64.size else 0.0,
            "pearson_r": r, "bit_identical": bool(np.array_equal(a, b))}


def extraction_drift(store: FeatureStore, input_sha256: str, extract: Extractor, predict: Predictor,
                     cached_preds: np.ndarray) -> dict[str, Any]:
    """Throw-away fresh extraction (never stored) vs the cache. Reported only (``gated: False``)."""
    meta = store.verify(input_sha256)
    e = store.entry_dir(input_sha256)
    with tempfile.TemporaryDirectory(prefix="yct_drift_") as td:
        clip = Path(td) / "input" / meta["input_name"]
        clip.parent.mkdir()
        shutil.copy2(e / "input" / meta["input_name"], clip)
        for s in SIDECAR_SUFFIXES:
            if (e / "input" / clip.with_suffix(s).name).exists():
                shutil.copy2(e / "input" / clip.with_suffix(s).name, clip.with_suffix(s))
        feat = Path(td) / "feat"
        feat.mkdir()
        with asr_guard():
            extract(clip, feat)
            fresh_preds, _ = predict(clip, feat)
        tensors = {}
        for rel in meta["tensors"]:
            f = feat / rel
            if not f.exists():
                tensors[rel] = {"present": False}
            elif rel.endswith(".npy"):
                tensors[rel] = _compare(np.load(e / "feat" / rel), np.load(f))
            else:
                tensors[rel] = {"bit_identical": sha256_file(f) == meta["tensors"][rel]["sha256"]}
    p = _compare(cached_preds, np.asarray(fresh_preds))
    store.verify(input_sha256, "after prediction")
    return {"gated": False, "pred_max_abs_diff": p.get("max_abs_diff"), "pred_pearson_r": p.get("pearson_r"),
            "pred_bit_identical": p.get("bit_identical", False), "pred_shape_match": p["shape_match"],
            "tensors": tensors}


def run_cached(video: str | Path, store: FeatureStore, extract: Extractor, predict: Predictor,
               revisions: dict[str, Any], out_prefix: str | Path,
               fresh_drift: bool = False) -> dict[str, Any]:
    """Extract-once + predict-from-cache. Writes <out_prefix>.npy and <out_prefix>.json (metrics).

    Returns the metrics dict plus ``aux`` (the predictor's auxiliary output, not serialised)."""
    out_prefix = Path(out_prefix)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    sha, meta, reused = store.ensure(video, extract, revisions)
    preds, aux = predict_cached(store, sha, predict)
    npy = Path(f"{out_prefix}.npy")
    np.save(npy, preds)
    m: dict[str, Any] = {
        "input_sha256": sha,
        "cache_entry": str(store.entry_dir(sha)),
        "cache_reused": reused,
        "revisions": meta["revisions"],
        "feature_sha256": {k: v["sha256"] for k, v in meta["tensors"].items()},
        "pred_shape": list(preds.shape),
        "pred_dtype": str(preds.dtype),
        "pred_sha256": sha256_file(npy),
    }
    if fresh_drift:
        m["fresh_extraction_drift"] = extraction_drift(store, sha, extract, predict, preds)
    Path(f"{out_prefix}.json").write_text(json.dumps(m, indent=1, sort_keys=True))
    return {**m, "aux": aux}
