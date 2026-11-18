"""FIX-P4E (D-063) feature-cache changes, CPU only (mock extractor/predictor):

* the cache key includes the extractor revisions, i.e. backbone revisions and the GPU model (v2.md P4:
  key = sha256(video || transcript || revisions || device class); Watchdog M2, Biostat D5, Referee m2);
* the D-038 fresh extraction can persist its predictions (Biostat P4-entry D4: Gate 2 re-scored on M1);
* a cache entry archived without media (S3 policy: no media in derived/) restores onto a new box from the
  tar + FILES_SHA256SUMS + the media files, verifies, and predicts bit-identically (QA P4-entry D9).
"""
from __future__ import annotations

import hashlib
import json
import tarfile
from pathlib import Path

import numpy as np
import pytest

from tests.test_tribe_feature_cache import REV, MockExtractor, MockPredictor
from yct.tribe_run import cache_archive as ca
from yct.tribe_run import feature_cache as fc

GPU_REV = {**REV, "gpu": "NVIDIA A100-SXM4-40GB",
           "backbones": {"facebook/vjepa2-vitg-fpc64-256": "875c192b", "meta-llama/Llama-3.2-3B": "13afe512"}}


def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


@pytest.fixture
def clip(tmp_path) -> Path:
    p = tmp_path / "in" / "abc.mp4"
    p.parent.mkdir()
    p.write_bytes(b"fake mp4 bytes " * 50)
    p.with_suffix(".tsv").write_text("text\tstart\tduration\tsequence_id\tsentence\nhi\t1.0\t0.2\t0\thi\n")
    return p


class WavWritingExtractor(MockExtractor):
    """Like TRIBE: also writes a sidecar <stem>.wav next to the cached clip copy (media, never archived)."""

    def __call__(self, video: Path, feat_dir: Path) -> None:
        super().__call__(video, feat_dir)
        video.with_suffix(".wav").write_bytes(b"RIFF fake wav " * 20)


# ---------------------------------------------------------------- cache key = video + transcript + revisions
def test_cache_key_includes_revisions_gpu_and_backbones(clip):
    k = fc.cache_key(clip, revisions=GPU_REV)
    assert k == fc.cache_key(clip, revisions=json.loads(json.dumps(GPU_REV)))   # canonical (order-free)
    assert k != fc.cache_key(clip, revisions={**GPU_REV, "gpu": "NVIDIA A100-SXM4-80GB"})
    assert k != fc.cache_key(clip, revisions={**GPU_REV, "backbones": {**GPU_REV["backbones"],
                                                                       "meta-llama/Llama-3.2-3B": "x"}})
    assert k != fc.cache_key(clip, revisions={**GPU_REV, "bug018_word_fix": True})
    with pytest.raises(TypeError):
        fc.cache_key(clip)  # revisions are mandatory: no key without the device class


def test_other_gpu_is_refused_in_one_root_and_gets_its_own_key(clip, tmp_path):
    store, ex = fc.FeatureStore(tmp_path / "c"), MockExtractor()
    m1 = fc.run_cached(clip, store, ex, MockPredictor(), GPU_REV, tmp_path / "o1")
    h100 = {**GPU_REV, "gpu": "NVIDIA H100"}
    with pytest.raises(fc.FeatureCacheError, match="never mix revisions"):
        fc.run_cached(clip, store, ex, MockPredictor(), h100, tmp_path / "o2")
    other = tmp_path / "other.mp4"                      # mixing is refused for any video in the root
    other.write_bytes(b"another clip")
    with pytest.raises(fc.FeatureCacheError, match="never mix revisions"):
        fc.run_cached(other, store, ex, MockPredictor(), h100, tmp_path / "o3")
    m2 = fc.run_cached(clip, fc.FeatureStore(tmp_path / "c2"), ex, MockPredictor(), h100, tmp_path / "o4")
    assert m2["cache_key"] != m1["cache_key"] and m2["cache_reused"] is False and ex.calls == 2
    assert m1["revisions"]["gpu"] == "NVIDIA A100-SXM4-40GB" and m2["revisions"]["gpu"] == "NVIDIA H100"


def test_run_clip_revisions_carry_gpu_backbones_and_bug018_flag(tmp_path):
    from types import SimpleNamespace

    from yct.tribe_run import run_clip

    (tmp_path / "best.ckpt").write_bytes(b"ckpt")
    tribev2 = SimpleNamespace(__file__=str(tmp_path / "pkg" / "tribev2" / "__init__.py"))
    torch = SimpleNamespace(__version__="2.6.0+cu124", version=SimpleNamespace(cuda="12.4"),
                            cuda=SimpleNamespace(get_device_name=lambda i: "NVIDIA A100-SXM4-40GB"))
    bb = {"facebook/w2v-bert-2.0": "da985ba0"}
    r_on = run_clip._revisions(tmp_path, tribev2, torch, bb, bug018_fix=True)
    r_off = run_clip._revisions(tmp_path, tribev2, torch, bb, bug018_fix=False)
    assert r_on["gpu"] == "NVIDIA A100-SXM4-40GB" and r_on["backbones"] == bb
    assert r_on["bug018_word_fix"] is True and r_off["bug018_word_fix"] is False
    assert r_on["ckpt_sha256"] == hashlib.sha256(b"ckpt").hexdigest()


# ---------------------------------------------------------------- D-038: persist fresh predictions
def test_fresh_predictions_are_saved_with_sha_but_never_reported(clip, tmp_path):
    store, ex, pr = fc.FeatureStore(tmp_path / "c"), MockExtractor(noise=1e-3), MockPredictor()
    m = fc.run_cached(clip, store, ex, pr, GPU_REV, tmp_path / "o1", fresh_drift=True,
                      keep_fresh=tmp_path / "o1.fresh_feat", fresh_preds_out=tmp_path / "o1.fresh_pred.npy")
    d = m["fresh_extraction_drift"]
    fresh = np.load(tmp_path / "o1.fresh_pred.npy")
    reported = np.load(tmp_path / "o1.npy")
    assert d["fresh_pred_sha256"] == _sha(tmp_path / "o1.fresh_pred.npy")
    assert fresh.shape == reported.shape and not np.array_equal(fresh, reported)   # fresh != cached
    assert m["pred_sha256"] == _sha(tmp_path / "o1.npy")
    assert (tmp_path / "o1.fresh_feat" / "audio.npy").exists()
    assert json.loads((store.entry_dir(m["cache_key"]) / fc.SIDECAR).read_text())["n_extractions"] == 1


# ---------------------------------------------------------------- archive (no media) -> restore -> predict
def _extracted(clip, tmp_path):
    store = fc.FeatureStore(tmp_path / "box1" / "fc")
    pr = MockPredictor()
    m = fc.run_cached(clip, store, WavWritingExtractor(), pr, GPU_REV, tmp_path / "box1" / "r1")
    return store, m


def test_archive_excludes_media_and_lists_every_file(clip, tmp_path):
    store, m = _extracted(clip, tmp_path)
    info = ca.archive_entry(store.root, m["cache_key"], tmp_path / "e.tar")
    with tarfile.open(tmp_path / "e.tar") as tf:
        names = tf.getnames()
    assert not [n for n in names if n.endswith(ca.MEDIA_SUFFIXES)]
    assert f"{m['cache_key']}/{fc.SIDECAR}" in names and f"{m['cache_key']}/input/abc.tsv" in names
    sums = ca.parse_sums(info["files_sha256sums"])
    assert f"{m['cache_key']}/input/abc.mp4" in sums and f"{m['cache_key']}/input/abc.wav" in sums
    assert sorted(x["path"] for x in info["media_excluded"]) == [f"{m['cache_key']}/input/abc.mp4",
                                                               f"{m['cache_key']}/input/abc.wav"]
    assert info["tar_sha256"] == _sha(tmp_path / "e.tar") and info["cache_key"] == m["cache_key"]
    assert all(x.endswith(ca.MEDIA_SUFFIXES) for x in info["media_files"].values())


def test_restore_roundtrip_verifies_and_predicts_bit_identically(clip, tmp_path):
    store, m = _extracted(clip, tmp_path)
    info = ca.archive_entry(store.root, m["cache_key"], tmp_path / "e.tar")
    media_dir = tmp_path / "pod_media"
    ca.save_media(store.root, m["cache_key"], media_dir)          # pod-side media store (not S3)
    new_root = tmp_path / "box2" / "fc"
    media = sorted(media_dir.iterdir())
    key = ca.restore_entry(tmp_path / "e.tar", info["files_sha256sums"], media, new_root)
    assert key == m["cache_key"]
    new = fc.FeatureStore(new_root)
    new.verify(key)
    ex2 = WavWritingExtractor()
    m2 = fc.run_cached(clip, new, ex2, MockPredictor(), GPU_REV, tmp_path / "box2" / "r1")
    assert ex2.calls == 0 and m2["cache_reused"] is True               # nothing re-extracted mid-campaign
    assert m2["pred_sha256"] == m["pred_sha256"]                       # Gate 1 across boxes


def test_restore_refuses_missing_media_wrong_sums_and_unsafe_paths(clip, tmp_path):
    store, m = _extracted(clip, tmp_path)
    info = ca.archive_entry(store.root, m["cache_key"], tmp_path / "e.tar")
    media_dir = tmp_path / "pod_media"
    ca.save_media(store.root, m["cache_key"], media_dir)
    media = sorted(media_dir.iterdir())
    with pytest.raises(ca.ArchiveError, match="media"):
        ca.restore_entry(tmp_path / "e.tar", info["files_sha256sums"], media[:1], tmp_path / "r1")
    bad = tmp_path / "other.mp4"
    bad.write_bytes(b"not the clip")
    with pytest.raises(ca.ArchiveError, match="media"):
        ca.restore_entry(tmp_path / "e.tar", info["files_sha256sums"], [bad, *media[1:]], tmp_path / "r2")
    lines = info["files_sha256sums"].splitlines()
    tampered = "\n".join(["0" * 64 + lines[0][64:], *lines[1:]]) + "\n"
    with pytest.raises(ca.ArchiveError, match="sha256"):
        ca.restore_entry(tmp_path / "e.tar", tampered, media, tmp_path / "r3")
    for root in ("r1", "r2", "r3"):      # nothing half-restored is left behind
        assert not (tmp_path / root / m["cache_key"]).exists()
    evil = tmp_path / "evil.tar"
    with tarfile.open(evil, "w") as tf:
        p = tmp_path / "x"
        p.write_text("x")
        tf.add(p, arcname="../escape")
    with pytest.raises(ca.ArchiveError, match="unsafe"):
        ca.restore_entry(evil, f"{'0' * 64}  ../escape\n", [], tmp_path / "r4")


def test_restore_over_existing_entry(clip, tmp_path):
    store, m = _extracted(clip, tmp_path)
    info = ca.archive_entry(store.root, m["cache_key"], tmp_path / "e.tar")
    media_dir = tmp_path / "pod_media"
    ca.save_media(store.root, m["cache_key"], media_dir)
    media = sorted(media_dir.iterdir())
    # identical entry already present -> no-op; a corrupt one -> refused (never overwritten)
    assert ca.restore_entry(tmp_path / "e.tar", info["files_sha256sums"], media, store.root) == m["cache_key"]
    np.save(store.entry_dir(m["cache_key"]) / "feat" / "audio.npy", np.zeros(3))
    with pytest.raises(fc.FeatureCacheError):
        ca.restore_entry(tmp_path / "e.tar", info["files_sha256sums"], media, store.root)


def test_archive_refuses_incomplete_entry(clip, tmp_path):
    store, m = _extracted(clip, tmp_path)
    (store.entry_dir(m["cache_key"]) / fc.MARKER).write_text("{}")
    with pytest.raises(fc.FeatureCacheError):
        ca.archive_entry(store.root, m["cache_key"], tmp_path / "e.tar")
