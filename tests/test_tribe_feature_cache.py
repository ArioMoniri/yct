"""BUG-006: TRIBE determinism by design. Features are extracted exactly once per input sha256 into a
content-addressed cache; predictions read only cached features; fresh-extraction drift is reported,
not gated. CPU only: the extractor (nondeterministic, like fp16 GPU backbones) and predictor are mocks.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from yct.transcribe import UnpinnedASRError
from yct.tribe_run import feature_cache as fc

REV = {"tribe_commit": "af58661", "hf_revision": "f894e78", "transformers": "5.17.0"}


def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class MockExtractor:
    """Writes two feature tensors; adds fresh noise on every call (GPU fp16 nondeterminism)."""

    def __init__(self, noise: float = 1e-3):
        self.calls = 0
        self.noise = noise
        self.rng = np.random.default_rng(20261117)

    def __call__(self, video: Path, feat_dir: Path) -> None:
        self.calls += 1
        base = np.frombuffer(Path(video).read_bytes()[:64].ljust(64, b"\0"), dtype=np.uint8)
        base = base.astype(np.float32) / 255.0
        v = np.tile(base, (10, 1)) + self.noise * self.rng.standard_normal((10, 64)).astype(np.float32)
        a = v[:, :16] * 2 + self.noise * self.rng.standard_normal((10, 16)).astype(np.float32)
        (feat_dir / "video").mkdir(parents=True, exist_ok=True)
        np.save(feat_dir / "video" / "vjepa.npy", v.astype(np.float32))
        np.save(feat_dir / "audio.npy", a.astype(np.float32))


class MockPredictor:
    """Deterministic linear readout of whatever features are in feat_dir."""

    def __init__(self):
        self.calls = 0
        self.seen: list[Path] = []
        self.w = np.random.default_rng(7).standard_normal((80, 20)).astype(np.float32)

    def __call__(self, video: Path, feat_dir: Path):
        self.calls += 1
        self.seen.append(Path(feat_dir))
        x = np.concatenate([np.load(feat_dir / "video" / "vjepa.npy"), np.load(feat_dir / "audio.npy")], 1)
        return x @ self.w, {"segments": list(range(x.shape[0]))}


@pytest.fixture
def clip(tmp_path) -> Path:
    p = tmp_path / "in" / "abc.mp4"
    p.parent.mkdir()
    p.write_bytes(b"fake mp4 bytes " * 50)
    p.with_suffix(".tsv").write_text("text\tstart\tduration\tsequence_id\tsentence\n")
    return p


@pytest.fixture
def store(tmp_path) -> fc.FeatureStore:
    return fc.FeatureStore(tmp_path / "cache")


def test_first_run_extracts_once_and_records_hashes(clip, store, tmp_path):
    ex, pr = MockExtractor(), MockPredictor()
    m = fc.run_cached(clip, store, ex, pr, REV, tmp_path / "out" / "r1")
    assert ex.calls == 1 and pr.calls == 1
    assert m["cache_reused"] is False and m["input_sha256"] == _sha(clip)
    entry = store.entry_dir(_sha(clip))
    meta = json.loads((entry / fc.SIDECAR).read_text())
    assert meta["input_sha256"] == _sha(clip)
    assert meta["revisions"] == REV and meta["n_extractions"] == 1
    assert set(meta["tensors"]) == {"video/vjepa.npy", "audio.npy"}
    for rel, t in meta["tensors"].items():
        assert t["sha256"] == _sha(entry / "feat" / rel)
    assert meta["tensors"]["video/vjepa.npy"]["shape"] == [10, 64]
    assert meta["tensors"]["audio.npy"]["dtype"] == "float32"
    assert m["feature_sha256"] == {k: v["sha256"] for k, v in meta["tensors"].items()}
    assert pr.seen == [entry / "feat"]  # prediction read the cache, not a fresh dir
    assert _sha(tmp_path / "out" / "r1.npy") == m["pred_sha256"]


def test_second_run_reuses_cache_and_is_bit_identical(clip, store, tmp_path):
    ex, pr = MockExtractor(), MockPredictor()
    m1 = fc.run_cached(clip, store, ex, pr, REV, tmp_path / "out" / "r1")
    m2 = fc.run_cached(clip, store, ex, pr, REV, tmp_path / "out" / "r2")
    assert ex.calls == 1, "features must be extracted exactly once per input sha256"
    assert pr.calls == 2
    assert m1["cache_reused"] is False and m2["cache_reused"] is True
    p1, p2 = np.load(tmp_path / "out" / "r1.npy"), np.load(tmp_path / "out" / "r2.npy")
    assert p1.dtype == p2.dtype and np.array_equal(p1, p2)
    assert float(np.max(np.abs(p1 - p2))) == 0.0
    assert m1["pred_sha256"] == m2["pred_sha256"] == _sha(tmp_path / "out" / "r2.npy")
    assert m1["feature_sha256"] == m2["feature_sha256"]


def test_new_store_object_same_root_reuses(clip, tmp_path):
    ex = MockExtractor()
    fc.run_cached(clip, fc.FeatureStore(tmp_path / "c"), ex, MockPredictor(), REV, tmp_path / "o1")
    fc.run_cached(clip, fc.FeatureStore(tmp_path / "c"), ex, MockPredictor(), REV, tmp_path / "o2")
    assert ex.calls == 1


def test_cache_is_keyed_by_content_not_name(clip, store, tmp_path):
    ex = MockExtractor()
    fc.run_cached(clip, store, ex, MockPredictor(), REV, tmp_path / "o1")
    renamed = tmp_path / "other" / "zzz.mp4"
    renamed.parent.mkdir()
    renamed.write_bytes(clip.read_bytes())
    m = fc.run_cached(renamed, store, ex, MockPredictor(), REV, tmp_path / "o2")
    assert ex.calls == 1 and m["cache_reused"] is True
    changed = tmp_path / "other" / "new.mp4"
    changed.write_bytes(clip.read_bytes() + b"x")
    fc.run_cached(changed, store, ex, MockPredictor(), REV, tmp_path / "o3")
    assert ex.calls == 2


def test_tampered_tensor_fails_loudly(clip, store, tmp_path):
    ex = MockExtractor()
    fc.run_cached(clip, store, ex, MockPredictor(), REV, tmp_path / "o1")
    t = store.entry_dir(_sha(clip)) / "feat" / "audio.npy"
    arr = np.load(t)
    arr[0, 0] += 1.0
    np.save(t, arr)
    with pytest.raises(fc.FeatureCacheError, match="audio.npy"):
        fc.run_cached(clip, store, ex, MockPredictor(), REV, tmp_path / "o2")
    assert ex.calls == 1  # never silently re-extracts


def test_extra_or_missing_cached_file_fails(clip, store, tmp_path):
    ex = MockExtractor()
    fc.run_cached(clip, store, ex, MockPredictor(), REV, tmp_path / "o1")
    feat = store.entry_dir(_sha(clip)) / "feat"
    (feat / "stray.npy").write_bytes(b"x")
    with pytest.raises(fc.FeatureCacheError, match="stray"):
        fc.run_cached(clip, store, ex, MockPredictor(), REV, tmp_path / "o2")
    (feat / "stray.npy").unlink()
    (feat / "audio.npy").unlink()
    with pytest.raises(fc.FeatureCacheError, match="audio.npy"):
        fc.run_cached(clip, store, ex, MockPredictor(), REV, tmp_path / "o3")


def test_revision_mismatch_refuses(clip, store, tmp_path):
    ex = MockExtractor()
    fc.run_cached(clip, store, ex, MockPredictor(), REV, tmp_path / "o1")
    with pytest.raises(fc.FeatureCacheError, match="revision"):
        fc.run_cached(clip, store, ex, MockPredictor(), {**REV, "transformers": "5.18.0"}, tmp_path / "o2")
    assert ex.calls == 1


def test_incomplete_entry_refuses(clip, store, tmp_path):
    def boom(video, feat_dir):
        (feat_dir / "half.npy").write_bytes(b"partial")
        raise RuntimeError("GPU died mid-extraction")

    with pytest.raises(RuntimeError, match="GPU died"):
        fc.run_cached(clip, store, boom, MockPredictor(), REV, tmp_path / "o1")
    with pytest.raises(fc.FeatureCacheError, match="incomplete"):
        fc.run_cached(clip, store, MockExtractor(), MockPredictor(), REV, tmp_path / "o2")


def test_prediction_must_not_write_to_cache(clip, store, tmp_path):
    ex = MockExtractor()

    def sneaky(video, feat_dir):  # e.g. a predictor that silently re-extracts features
        ex(video, feat_dir)
        return np.zeros((10, 20), np.float32), {}

    with pytest.raises(fc.FeatureCacheError, match="modified"):
        fc.run_cached(clip, store, ex, sneaky, REV, tmp_path / "o1")


def test_prediction_must_not_add_files_to_cache(clip, store, tmp_path):
    def adds(video, feat_dir):
        (feat_dir / "new_feature.npy").write_bytes(b"x")
        return np.zeros((10, 20), np.float32), {}

    with pytest.raises(fc.FeatureCacheError, match="new_feature"):
        fc.run_cached(clip, store, MockExtractor(), adds, REV, tmp_path / "o1")


def test_fresh_extraction_drift_is_reported_not_gated(clip, store, tmp_path):
    ex, pr = MockExtractor(noise=1e-3), MockPredictor()
    m1 = fc.run_cached(clip, store, ex, pr, REV, tmp_path / "o1")
    m2 = fc.run_cached(clip, store, ex, pr, REV, tmp_path / "o2", fresh_drift=True)
    d = m2["fresh_extraction_drift"]
    assert d["gated"] is False
    assert d["pred_max_abs_diff"] > 0 and d["pred_bit_identical"] is False
    assert 0.99 < d["pred_pearson_r"] < 1.0
    assert set(d["tensors"]) == {"video/vjepa.npy", "audio.npy"}
    assert d["tensors"]["audio.npy"]["max_abs_diff"] > 0
    assert m2["pred_sha256"] == m1["pred_sha256"]  # drift never leaks into the reported predictions
    assert ex.calls == 2  # one cached extraction + one throw-away fresh one
    meta = json.loads((store.entry_dir(_sha(clip)) / fc.SIDECAR).read_text())
    assert meta["n_extractions"] == 1  # the throw-away extraction is not stored
    assert json.loads((tmp_path / "o2.json").read_text())["fresh_extraction_drift"] == d


def test_deterministic_extractor_has_zero_drift(clip, store, tmp_path):
    ex = MockExtractor(noise=0.0)
    m = fc.run_cached(clip, store, ex, MockPredictor(), REV, tmp_path / "o1", fresh_drift=True)
    d = m["fresh_extraction_drift"]
    assert d["pred_bit_identical"] is True and d["pred_max_abs_diff"] == 0.0


def test_asr_guard_wraps_extraction_and_prediction(clip, store, tmp_path):
    def asr_extract(video, feat_dir):
        subprocess.run(["uvx", "whisperx", str(video)], check=False)

    with pytest.raises(UnpinnedASRError):
        fc.run_cached(clip, store, asr_extract, MockPredictor(), REV, tmp_path / "o1")

    ex = MockExtractor()

    def asr_predict(video, feat_dir):
        subprocess.Popen(["whisperx", str(video)])

    store2 = fc.FeatureStore(tmp_path / "c2")
    with pytest.raises(UnpinnedASRError):
        fc.run_cached(clip, store2, ex, asr_predict, REV, tmp_path / "o2")


def test_input_copy_and_transcript_are_cached_and_hashed(clip, store, tmp_path):
    seen = {}

    def ex(video, feat_dir):
        seen["video"] = Path(video)
        MockExtractor()(video, feat_dir)

    fc.run_cached(clip, store, ex, MockPredictor(), REV, tmp_path / "o1")
    entry = store.entry_dir(_sha(clip))
    assert seen["video"].parent == entry / "input" and seen["video"].name == clip.name
    meta = json.loads((entry / fc.SIDECAR).read_text())
    assert meta["input_files"][clip.name] == _sha(clip)
    assert meta["input_files"]["abc.tsv"] == _sha(clip.with_suffix(".tsv"))
