"""Content-addressed TRIBE feature cache: determinism by design (BUG-006).

P0 (run smoke_20261117T142354Z) showed that two fresh TRIBE runs differ (max 3.57e-3) because the GPU
feature extractors (fp16 backbones) are nondeterministic, while re-predicting from cached features is
bit-identical. So:

* features are extracted EXACTLY ONCE per cache key = sha256(video sha256 + transcript sha256, or
  "none" without a transcript) into ``<root>/<key>/`` (``input/`` holds the clip copy + transcript,
  ``feat/`` the extractor's tensors), and a sidecar ``features.meta.json`` records the sha256 (and
  shape/dtype for .npy) of every cached file plus the extractor revisions. A transcript added, removed
  or changed therefore gets its own entry (Biostat P0 P3: never reuse text-less features);
* every prediction (reruns, ablations, controls) reads only the cache. The cache is re-hashed before
  and after each prediction; any change, missing or new file raises ``FeatureCacheError`` (so a
  predictor that silently re-extracts cannot go unnoticed);
* fresh-extraction drift (throw-away re-extraction vs the cache) is measured per cached feature
  tensor and per extractor; D-038 gates it on reliability >= RELIABILITY_GATE (0.99) per feature
  (``reliability_gate_pass``), while the reported predictions never use the fresh extraction;
* ``offline=True`` additionally blocks all non-loopback network access while extracting and predicting
  (BUG-003, ``yct.tribe_run.offline.no_network``).

Extraction and prediction both run inside ``yct.transcribe.asr_guard()`` (no unpinned WhisperX).
The extractor/predictor are callables so the logic is tested on CPU with mocks
(tests/test_tribe_feature_cache.py); ``run_clip.py`` supplies the TRIBE implementations.

    extract(video: Path, feat_dir: Path) -> None          # writes feature files under feat_dir
    predict(video: Path, feat_dir: Path) -> (preds, aux)  # preds: np.ndarray (T, V); aux: anything
"""
from __future__ import annotations

import contextlib
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
RELIABILITY_GATE = 0.99       # D-038: fresh re-extraction reliability per feature must be >= this

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


def transcript_sha256(video: str | Path) -> str | None:
    tsv = Path(video).with_suffix(".tsv")
    return sha256_file(tsv) if tsv.exists() else None


def cache_key(video: str | Path, video_sha256: str | None = None) -> str:
    """sha256 over the video sha256 and the transcript sha256 ("none" if there is no <stem>.tsv)."""
    vsha = video_sha256 or sha256_file(video)
    tsha = transcript_sha256(video) or "none"
    return hashlib.sha256(f"yct-feature-cache-v2\nvideo:{vsha}\ntranscript:{tsha}\n".encode()).hexdigest()


def _net(offline: bool):
    """no_network() when offline (BUG-003), else a no-op context."""
    if not offline:
        return contextlib.nullcontext()
    from yct.tribe_run.offline import no_network

    return no_network()


class FeatureStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser()

    def entry_dir(self, key: str) -> Path:
        return self.root / key

    def manifest(self) -> dict[str, Any]:
        """{cache_key: {input_sha256, transcript_sha256, sidecar_sha256, tensors}} for every entry."""
        out = {}
        for side in sorted(self.root.glob(f"*/{SIDECAR}")):
            meta = json.loads(side.read_text())
            out[side.parent.name] = {
                "input_sha256": meta["input_sha256"], "transcript_sha256": meta.get("transcript_sha256"),
                "input_name": meta["input_name"], "sidecar_sha256": sha256_file(side),
                "tensors": {k: v["sha256"] for k, v in meta["tensors"].items()},
                "input_files": meta["input_files"], "revisions": meta["revisions"],
            }
        return out

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

    def ensure(self, video: str | Path, extract: Extractor, revisions: dict[str, Any],
               offline: bool = False) -> tuple[str, dict[str, Any], bool]:
        """Return (cache_key, meta, reused). Extracts only if no entry exists for the cache key
        (video sha256 + transcript sha256)."""
        video = Path(video)
        vsha = sha256_file(video)
        sha = cache_key(video, vsha)
        meta = self.meta(sha)
        if meta is not None:
            if meta["revisions"] != revisions:
                raise FeatureCacheError(
                    f"extractor revision mismatch for {sha}: cached {meta['revisions']} vs requested "
                    f"{revisions}; never mix revisions (use a new cache root)")
            for sc in _sidecars(video):
                cached = meta["input_files"].get(Path(meta["input_name"]).with_suffix(sc.suffix).name)
                if cached != sha256_file(sc):
                    raise FeatureCacheError(f"{sc.name} differs from the transcript cached for {sha}")
            if meta.get("input_sha256") != vsha:
                raise FeatureCacheError(f"cache entry {sha} holds a different video")
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
            with _net(offline):
                extract(clip, e / "feat")
        feat = _hash_tree(e / "feat")
        if not feat:
            raise FeatureCacheError(f"extractor wrote no features for {sha}")
        meta = {
            "input_sha256": vsha,
            "transcript_sha256": transcript_sha256(video),
            "cache_key": sha,
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


def predict_cached(store: FeatureStore, input_sha256: str, predict: Predictor,
                   offline: bool = False) -> tuple[np.ndarray, Any]:
    meta = store.verify(input_sha256, "before prediction")
    e = store.entry_dir(input_sha256)
    with asr_guard():
        with _net(offline):
            preds, aux = predict(e / "input" / meta["input_name"], e / "feat")
    store.verify(input_sha256, "after prediction")
    return np.asarray(preds), aux


def _compare(a: np.ndarray, b: np.ndarray) -> dict[str, Any]:
    a64, b64 = np.asarray(a, np.float64).ravel(), np.asarray(b, np.float64).ravel()
    if a64.shape != b64.shape:
        return {"shape_match": False}
    r = float(np.corrcoef(a64, b64)[0, 1]) if a64.size > 1 and a64.std() > 0 and b64.std() > 0 else None
    return {"shape_match": True, "max_abs_diff": float(np.max(np.abs(a64 - b64))) if a64.size else 0.0,
            "pearson_r": r, "reliability": reliability(a64, b64), "bit_identical": bool(np.array_equal(a, b))}


def reliability(a: np.ndarray, b: np.ndarray) -> float | None:
    """Test-retest reliability of two extractions: 1 - var(a - b) / (var(a) + var(b)).

    With b = a + e (independent extraction noise) this is sigma_true^2 / (sigma_true^2 + sigma_e^2)
    (Biostat P0: 1 - r = sigma_e^2 / sigma_tot^2); 1.0 when identical, None when both are constant."""
    a = np.asarray(a, np.float64).ravel()
    b = np.asarray(b, np.float64).ravel()
    den = a.var() + b.var()
    if a.shape != b.shape or not a.size:
        return None
    if den == 0:
        return 1.0 if np.array_equal(a, b) else None
    return float(1.0 - np.var(a - b) / den)


def _as_array(v: Any) -> np.ndarray | None:
    """numpy copy of an in-memory value: ndarray / memmap, torch tensor, or anything with __array__."""
    if hasattr(v, "detach"):
        v = v.detach().cpu().numpy()
    if isinstance(v, np.ndarray):
        return np.array(v)
    if hasattr(v, "__array__"):
        a = np.asarray(v)
        return None if a.dtype == object else np.array(a)
    inner = getattr(v, "data", None)
    if inner is not None and not isinstance(inner, bytes | memoryview):
        return _as_array(inner)
    return None


def _norm_key(key: str) -> str:
    """Cache keys of the audio/video extractors embed the absolute input path (cache entry or throw-away
    dir); keep only the part from ``input/`` on so cached and fresh extractions pair up."""
    k = str(key)
    i = k.rfind("/input/")
    return k[i + 1:] if i >= 0 else k


def _memmap_specs(obj: Any, path: str = "") -> list[tuple[str, dict]]:
    """Every {"#type": "MemmapArray", filename, offset, shape, dtype} spec inside one info record."""
    out: list[tuple[str, dict]] = []
    if isinstance(obj, dict):
        if obj.get("#type") == "MemmapArray" and "filename" in obj:
            return [(path, obj)]
        for k, v in obj.items():
            if not str(k).startswith("#"):
                out += _memmap_specs(v, f"{path}::{k}" if path else str(k))
    return out


def _exca_arrays(feat_dir: Path) -> tuple[dict[str, np.ndarray], list[str]]:
    """Arrays of exca CacheDicts (folders holding ``*-info.jsonl``), read directly from the info records +
    data files with numpy (read-only memmaps; no exca/neuralset import, so it also runs on the pod/CPU).
    Returns (arrays, unreadable record names): any record without a readable array is reported, never
    silently skipped (the D-038 gate then fails)."""
    out: dict[str, np.ndarray] = {}
    bad: list[str] = []
    for info in sorted(feat_dir.rglob("*-info.jsonl")):
        folder = info.parent
        rel = folder.relative_to(feat_dir).as_posix()
        for line in info.read_text().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            key = rec.get("#key")
            if key is None:
                continue
            name = f"{rel}::{_norm_key(key)}"
            specs = _memmap_specs(rec)
            if not specs:
                bad.append(name)
                continue
            for sub, spec in specs:
                f = folder / spec["filename"]
                try:
                    arr = np.memmap(f, dtype=np.dtype(spec["dtype"]), mode="r",
                                    offset=int(spec.get("offset", 0)), shape=tuple(spec["shape"]), order="C")
                except (OSError, ValueError, TypeError):
                    bad.append(name + (f"::{sub}" if sub else ""))
                    continue
                out[name + (f"::{sub}" if sub and sub != "data" else "")] = np.array(arr)
    return out, bad


def load_feature_arrays(feat_dir: str | Path, unreadable: list[str] | None = None) -> dict[str, np.ndarray]:
    """Every numeric feature array under feat_dir: .npy files plus exca CacheDict records. Names of
    records that hold no readable array are appended to `unreadable`."""
    feat_dir = Path(feat_dir)
    out = {p.relative_to(feat_dir).as_posix(): np.load(p, allow_pickle=False)
           for p in sorted(feat_dir.rglob("*.npy"))}
    exca, bad = _exca_arrays(feat_dir)
    out.update(exca)
    if unreadable is not None:
        unreadable += bad
    return out


def _extractor_of(name: str) -> str:
    """Feature group of an array name: the exca folder, else the first path component."""
    if "::" in name:
        return name.split("::", 1)[0]
    return name.split("/", 1)[0] if "/" in name else name


def feature_reliability(cached_feat: Path, fresh_feat: Path) -> dict[str, Any]:
    """Per-array and per-extractor reliability of a fresh extraction vs the cache (D-038 gate)."""
    bad_a: list[str] = []
    bad_b: list[str] = []
    a, b = load_feature_arrays(cached_feat, bad_a), load_feature_arrays(fresh_feat, bad_b)
    arrays: dict[str, Any] = {}
    groups: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {}
    for name in sorted(set(a) | set(b)):
        if name not in a or name not in b:
            arrays[name] = {"present_in_both": False}
            continue
        arrays[name] = _compare(a[name], b[name])
        if arrays[name].get("shape_match"):
            groups.setdefault(_extractor_of(name), []).append((a[name], b[name]))
    per_extractor = {}
    for g, pairs in groups.items():
        x = np.concatenate([np.asarray(p, np.float64).ravel() for p, _ in pairs])
        y = np.concatenate([np.asarray(q, np.float64).ravel() for _, q in pairs])
        per_extractor[g] = {"n_arrays": len(pairs), "reliability": reliability(x, y),
                            "max_abs_diff": float(np.max(np.abs(x - y))) if x.size else 0.0,
                            "bit_identical": bool(np.array_equal(x, y))}
    rel = [v["reliability"] for v in arrays.values() if v.get("reliability") is not None]
    complete = bool(arrays) and all(v.get("present_in_both", True) and v.get("shape_match", False)
                                    for v in arrays.values())
    rmin = min(rel) if rel else None
    unreadable = sorted(set(bad_a) | set(bad_b))
    return {"n_arrays": len(arrays), "arrays": arrays, "per_extractor": per_extractor,
            "unreadable": unreadable, "reliability_min": rmin, "reliability_gate": RELIABILITY_GATE,
            "reliability_gate_pass": bool(complete and not unreadable and rmin is not None
                                          and rmin >= RELIABILITY_GATE)}


def extraction_drift(store: FeatureStore, input_sha256: str, extract: Extractor, predict: Predictor,
                     cached_preds: np.ndarray, offline: bool = False,
                     keep_fresh: str | Path | None = None) -> dict[str, Any]:
    """Throw-away fresh extraction (never stored) vs the cache. The reported predictions are never
    affected (``gated: False`` for them); ``feature_reliability`` carries the D-038 per-feature gate."""
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
            with _net(offline):
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
        feat_rel = feature_reliability(e / "feat", feat)
        if keep_fresh is not None:  # audit copy of the throw-away extraction (never used for predictions)
            shutil.copytree(feat, Path(keep_fresh), dirs_exist_ok=False)
            feat_rel["fresh_features_kept_at"] = str(keep_fresh)
    p = _compare(cached_preds, np.asarray(fresh_preds))
    store.verify(input_sha256, "after prediction")
    return {"gated": False, "pred_max_abs_diff": p.get("max_abs_diff"), "pred_pearson_r": p.get("pearson_r"),
            "pred_bit_identical": p.get("bit_identical", False), "pred_shape_match": p["shape_match"],
            "pred_reliability": p.get("reliability"), "tensors": tensors, "feature_reliability": feat_rel}


def run_cached(video: str | Path, store: FeatureStore, extract: Extractor, predict: Predictor,
               revisions: dict[str, Any], out_prefix: str | Path,
               fresh_drift: bool = False, offline: bool = False,
               keep_fresh: str | Path | None = None) -> dict[str, Any]:
    """Extract-once + predict-from-cache. Writes <out_prefix>.npy and <out_prefix>.json (metrics).

    Returns the metrics dict plus ``aux`` (the predictor's auxiliary output, not serialised)."""
    out_prefix = Path(out_prefix)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    sha, meta, reused = store.ensure(video, extract, revisions, offline=offline)
    preds, aux = predict_cached(store, sha, predict, offline=offline)
    npy = Path(f"{out_prefix}.npy")
    np.save(npy, preds)
    m: dict[str, Any] = {
        "input_sha256": meta["input_sha256"],
        "transcript_sha256": meta.get("transcript_sha256"),
        "cache_key": sha,
        "offline": offline,
        "cache_entry": str(store.entry_dir(sha)),
        "cache_reused": reused,
        "revisions": meta["revisions"],
        "feature_sha256": {k: v["sha256"] for k, v in meta["tensors"].items()},
        "pred_shape": list(preds.shape),
        "pred_dtype": str(preds.dtype),
        "pred_sha256": sha256_file(npy),
    }
    if fresh_drift:
        m["fresh_extraction_drift"] = extraction_drift(store, sha, extract, predict, preds, offline=offline,
                                                       keep_fresh=keep_fresh)
    Path(f"{out_prefix}.json").write_text(json.dumps(m, indent=1, sort_keys=True))
    return {**m, "aux": aux}
