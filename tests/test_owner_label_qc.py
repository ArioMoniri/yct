"""Pure-python parts of scripts/owner_label_qc.sh (FIX-P1, D-047): kappa, block coding, table loading,
output hygiene. Synthetic data only; the embedded module is extracted from the shell script."""
import importlib.util
import math
import random
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SH = ROOT / "scripts" / "owner_label_qc.sh"
ACC, REJ = "acc" + "epted", "rej" + "ected"


@pytest.fixture(scope="module")
def qc(tmp_path_factory):
    text = SH.read_text()
    m = re.search(r"<<'PYQC'\n(.*?)\nPYQC\n", text, re.S)
    assert m, "embedded python block not found"
    p = tmp_path_factory.mktemp("qc") / "qc.py"
    p.write_text(m.group(1))
    spec = importlib.util.spec_from_file_location("owner_qc", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.__file__ = str(p)
    return mod


def test_shell_syntax():
    assert subprocess.run(["bash", "-n", str(SH)]).returncode == 0


def test_min_videos_matches_config(qc):
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    assert qc.ROUTE_MERGE_MIN_VIDEOS == cfg["era_blocks"]["route_merge_min_videos"]
    assert set(qc.ERA_ORDER) - {"UNKNOWN"} == set(cfg["era_blocks"]["merge"])


# ---------------------------------------------------------------- kappa
def test_kappa_known_value(qc):
    # 2x2 table [[20, 5], [10, 15]]: po = .7, pe = .5 -> kappa .4
    a = ["x"] * 25 + ["y"] * 25
    b = ["x"] * 20 + ["y"] * 5 + ["x"] * 10 + ["y"] * 15
    k, po, pe = qc.cohen_kappa(a, b)
    assert po == pytest.approx(0.7) and pe == pytest.approx(0.5) and k == pytest.approx(0.4)
    lo, hi = qc.kappa_ci(po, pe, 50)
    assert lo < 0.4 < hi
    assert hi - lo == pytest.approx(2 * 1.96 * math.sqrt(0.7 * 0.3 / (50 * 0.25)))


def test_kappa_perfect_and_one_disagreement_of_58(qc):
    a = ["x"] * 30 + ["y"] * 28
    assert qc.cohen_kappa(a, list(a))[0] == pytest.approx(1.0)
    b = list(a)
    b[0] = "y"
    assert qc.cohen_kappa(a, b)[0] == pytest.approx(0.9655, abs=1e-3)   # Biostat P1 #7: ~0.97


def test_kappa_undefined_when_constant(qc):
    k, po, pe = qc.cohen_kappa(["x"] * 5, ["x"] * 5)
    assert math.isnan(k) and po == 1
    with pytest.raises(ValueError):
        qc.cohen_kappa(["x"], [])


def test_compare_reports_ids_only(qc):
    ids = [f"yct_{i:04d}" for i in range(1, 11)]
    sealed = {v: {"outcome": ACC if i < 5 else REJ, "label_confidence": "A"} for i, v in enumerate(ids)}
    red = {v: {"outcome": r["outcome"], "label_confidence": "A"} for v, r in sealed.items()}
    red["yct_0002"]["outcome"] = REJ
    red["yct_0003"]["label_confidence"] = "B"
    del red["yct_0010"]
    res = qc.compare(sealed, red, ids)
    assert res["n"] == 9 and res["missing"] == ["yct_0010"] and res["disagree"] == ["yct_0002"]
    assert res["not_conf_a"] == ["yct_0003"]
    out = qc.format_compare(res)
    assert ACC not in out and REJ not in out
    assert "yct_0002" in out and "kappa" in out


def test_compare_aborts_without_sealed_label(qc):
    with pytest.raises(SystemExit):
        qc.compare({"yct_0001": {"outcome": ACC}}, {}, ["yct_0001", "yct_0002"])


# ---------------------------------------------------------------- block coding
def test_merge_within_route_rule(qc):
    assert qc.merge_within_route({"E12": 3, "E3": 40}) == {"E12": "E12+E3", "E3": "E12+E3"}
    assert qc.merge_within_route({"E12": 6, "E3": 40}) == {"E12": "E12", "E3": "E3"}
    assert qc.merge_within_route({"E3": 4, "E12": 9}) == {"E12": "E12+E3", "E3": "E12+E3"}
    assert qc.merge_within_route({"E12": 2}) == {"E12": "E12"}           # single block kept even if small
    m = qc.merge_within_route({"E12": 10, "E3": 10, "UNKNOWN": 2})
    assert m == {"E12": "E12", "E3": "E3+UNKNOWN", "UNKNOWN": "E3+UNKNOWN"}


def _rows():
    rows = [(f"yct_{i:04d}", "E12", "OPEN") for i in range(3)]
    rows += [(f"yct_{i:04d}", "E3", "OPEN") for i in range(3, 30)]
    rows += [(f"yct_{i:04d}", "E12", "TARGETED") for i in range(30, 37)]
    rows += [(f"yct_{i:04d}", "E3", "TARGETED") for i in range(37, 58)]
    return rows


def test_block_codes_merge_within_route_never_across(qc):
    codes = qc.block_codes(_rows(), salt="s1")
    assert set(codes) == {r[0] for r in _rows()}
    assert sorted(set(codes.values())) == ["B1", "B2", "B3"]
    route = {v: r for v, _, r in _rows()}
    for c in set(codes.values()):
        assert len({route[v] for v, cc in codes.items() if cc == c}) == 1     # a code never spans routes
    open_codes = {codes[v] for v, _, r in _rows() if r == "OPEN"}
    assert len(open_codes) == 1                                             # OPEN E12 (3) merged into E3


def test_block_codes_opaque_and_salted(qc):
    a = qc.block_codes(_rows(), salt="s1")
    assert a == qc.block_codes(_rows(), salt="s1")                          # deterministic given the salt
    seen = set()
    for s in range(40):
        c = qc.block_codes(_rows(), salt=f"salt{s}")
        seen.add(c["yct_0000"])
        sizes = sorted(list(c.values()).count(k) for k in set(c.values()))
        assert sizes == [7, 21, 30]                                         # same partition, codes permuted
    assert len(seen) == 3                                                   # code number reveals nothing


def test_blocks_for_and_ssm_value(qc):
    manifest = [{"video_id": v, "era_block": e, "in_primary": "True"} for v, e, _ in _rows()]
    manifest.append({"video_id": "yct_0999", "era_block": "E3", "in_primary": "False"})
    sealed = {v: {"outcome": ACC, "route": r.lower()} for v, _, r in _rows()}
    codes, col = qc.blocks_for(manifest, sealed, salt="x")
    assert col == "route" and "yct_0999" not in codes
    val = qc.ssm_value(codes)
    assert re.fullmatch(r"(yct_\d{4}:B\d+)(,yct_\d{4}:B\d+)*", val)
    assert val.split(",")[0].startswith("yct_0000:")
    del sealed["yct_0005"]["route"]
    with pytest.raises(SystemExit):
        qc.blocks_for(manifest, sealed, salt="x")


# ---------------------------------------------------------------- tables, end to end
def _write_fixture(tmp_path):
    lab = tmp_path / "labels"
    (lab / "p1").mkdir(parents=True)
    (lab / "p1b").mkdir()
    (lab / "p1c").mkdir()
    ids = [v for v, _, _ in _rows()]
    rng = random.Random(0)
    out = {v: rng.choice([ACC, REJ]) for v in ids}
    route = {v: r for v, _, r in _rows()}
    (lab / "p1" / "labels.csv").write_text(
        "video_id,outcome,label_confidence,route,quote\n"
        + "".join(f"{v},{out[v]},A,{route[v]},q{v}\n" for v in ids[:40]))
    import json
    (lab / "p1b" / "part1.json").write_text(json.dumps(
        [{"video_id": v, "outcome": out[v], "label_confidence": "A", "route": route[v]} for v in ids[40:]]
        + [{"video_id": ids[0], "outcome": out[ids[0]]}]))                  # consistent duplicate is fine
    (lab / "p1c" / "urls.csv").write_text("file,id,url\nmanifest,yct_0001,https://example.org/real.mp4\n")
    red = tmp_path / "rederive"
    red.mkdir()
    flip = {ids[4]}
    (red / "rederive.csv").write_text("video_id,outcome,label_confidence\n" + "".join(
        f"{v},{(REJ if out[v] == ACC else ACC) if v in flip else out[v]},A\n" for v in ids))
    man = tmp_path / "manifest.csv"
    era = {v: e for v, e, _ in _rows()}
    man.write_text("video_id,url,era_block,in_primary\n" + "".join(
        f"{v},{'sealed:' + v if v == 'yct_0001' else 'https://youtu.be/' + v},{era[v]},True\n" for v in ids))
    return lab, red, man, ids


def test_end_to_end_kappa_blocks_spot(qc, tmp_path, capsys):
    lab, red, man, ids = _write_fixture(tmp_path)
    assert qc.main(["kappa", "--manifest", str(man), "--sealed", str(lab), "--rederive", str(red)]) == 0
    out = capsys.readouterr().out
    assert "compared n = 58" in out and ids[4] in out
    assert ACC not in out and REJ not in out
    blocks = tmp_path / "blocks.txt"
    assert qc.main(["blocks", "--manifest", str(man), "--sealed", str(lab), "--out", str(blocks)]) == 0
    out = capsys.readouterr().out
    assert "3 blocks over 58" in out and "OPEN" not in out and "TARGETED" not in out
    assert len(blocks.read_text().split(",")) == 58
    assert qc.main(["spot", "--manifest", str(man), "--sealed", str(lab), "--n", "10"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 10 and all("outcome=" in x for x in lines)


def test_spot_resolves_sealed_url(qc, tmp_path):
    lab, _, man, _ = _write_fixture(tmp_path)
    rows = qc.spot_rows(qc.read_manifest(man), qc.load_rows(lab, ("video_id", "outcome")),
                        qc.sealed_urls(lab), k=58, rng=random.Random(1))
    assert {r["video_id"]: r["url"] for r in rows}["yct_0001"] == "https://example.org/real.mp4"


def test_conflicting_sealed_tables_abort(qc, tmp_path):
    (tmp_path / "a.csv").write_text(f"video_id,outcome\nyct_0001,{ACC}\n")
    (tmp_path / "b.csv").write_text(f"video_id,outcome\nyct_0001,{REJ}\n")
    with pytest.raises(SystemExit, match="yct_0001"):
        qc.load_rows(tmp_path, ("video_id", "outcome"))


def test_verify_and_safe_extract(qc, tmp_path):
    import hashlib
    import tarfile
    enc = tmp_path / "enc"
    enc.mkdir()
    (enc / "x.tar.age").write_bytes(b"cipher")
    (enc / "x.tar.age.sha256").write_text(hashlib.sha256(b"cipher").hexdigest() + "  x.tar.age\n")
    qc.verify(enc)
    (enc / "x.tar.age").write_bytes(b"tampered")
    with pytest.raises(SystemExit, match="MISMATCH"):
        qc.verify(enc)
    bad = tmp_path / "bad.tar"
    with tarfile.open(bad, "w") as tf:
        info = tarfile.TarInfo("../escape.txt")
        info.size = 0
        tf.addfile(info)
    with pytest.raises(SystemExit, match="unsafe"):
        qc.safe_extract(bad, tmp_path / "dest")


def test_missing_route_defaults_to_keyword_search(qc, monkeypatch):
    """D-049: with explicit opt-in ROUTE_DEFAULT, empty routes are filled instead of aborting."""
    mod = qc
    monkeypatch.setenv("ROUTE_DEFAULT", "keyword_search")
    manifest = [{"video_id": f"v{i}", "in_primary": "True", "era_block": "E3"} for i in range(8)]
    sealed = {f"v{i}": {"discovery_method": ("" if i < 6 else "directory_sweep")} for i in range(8)}
    codes, col = mod.blocks_for(manifest, sealed, salt="x")
    assert col == "discovery_method" and set(codes) == {f"v{i}" for i in range(8)}
