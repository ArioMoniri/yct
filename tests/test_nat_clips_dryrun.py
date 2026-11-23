"""scripts/nat_clips_dryrun.py on fake pod dirs: present and sha-matching inputs pass; a missing transcript,
a wrong mp4/wav sha or a missing record are each named as a problem. No ffprobe (--no-probe path)."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("nat_clips_dryrun", ROOT / "scripts" / "nat_clips_dryrun.py")
dr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dr)


def fake(tmp: Path, n=2):
    t1, asr = tmp / "t1", tmp / "asr"
    (t1 / "audio16k").mkdir(parents=True)
    asr.mkdir()
    man = []
    for i in range(n):
        t = f"{i:016x}"
        (t1 / f"{t}.mp4").write_bytes(b"mp4" + bytes([i]))
        (t1 / "audio16k" / f"{t}.wav").write_bytes(b"wav" + bytes([i]))
        (t1 / f"{t}.json").write_text("{}")
        (asr / f"{t}.json").write_text("{}")
        man.append({"t1_name": t, "session": 0,
                    "t1_sha256": hashlib.sha256(b"mp4" + bytes([i])).hexdigest(),
                    "wav_sha256": hashlib.sha256(b"wav" + bytes([i])).hexdigest()})
    return man, t1, asr


def test_all_present_passes(tmp_path):
    man, t1, asr = fake(tmp_path)
    res = dr.check(man, t1, asr, do_probe=False)
    assert res["ok"] and res["n"] == 2 and [r["slot"] for r in res["rows"]] == ["nat_00", "nat_01"]


def test_each_defect_is_named(tmp_path):
    man, t1, asr = fake(tmp_path, 4)
    (asr / f"{man[0]['t1_name']}.json").unlink()
    (t1 / f"{man[1]['t1_name']}.mp4").write_bytes(b"other")
    (t1 / "audio16k" / f"{man[2]['t1_name']}.wav").write_bytes(b"other")
    (t1 / f"{man[3]['t1_name']}.json").unlink()
    res = dr.check(man, t1, asr, do_probe=False)
    assert not res["ok"]
    assert set(res["problems"]) == {f"{man[0]['t1_name']}: transcript", f"{man[1]['t1_name']}: mp4_sha_ok",
                                    f"{man[2]['t1_name']}: wav_sha_ok", f"{man[3]['t1_name']}: record"}


def test_missing_mp4_is_named(tmp_path):
    man, t1, asr = fake(tmp_path, 1)
    (t1 / f"{man[0]['t1_name']}.mp4").unlink()
    res = dr.check(man, t1, asr, do_probe=False)
    assert res["problems"] == [f"{man[0]['t1_name']}: mp4", f"{man[0]['t1_name']}: mp4_sha_ok"]
