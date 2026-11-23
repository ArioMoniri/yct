#!/usr/bin/env python3
"""D-085 part 2 step 4 (D-089 rates): build SPK + BURST (with the GREY_CTRL control) on the pod CPU, then
run the frozen QC. Texts stay private (never printed, never committed); numbers only; nobody listens.

  python scripts/speech_build.py OUT_DIR

Preconditions (each refuses, exit 1): the speech / TALKFACE / corpus / T-ENV keys frozen
(speech_corpus.speech_build_preconditions), the D-085 qc key frozen, controls.refclips_d089 frozen, the
selection record's sha frozen and equal to the committed file, no v1 SPK keep carried over.
Texts: the private raw page (speech.private_raw_s3) -> resolve_texts (raw sha + every item sha) ->
speech_build.reconstruct_texts. Engine: EspeakSynth (pin verified first), rates from the selection record
(speech_corpus.build_rates == effective_spec).
Build: refclips58.clip_audio / clip_frames / encode for grey_ctrl_00, spk_*, burst_*; the rendered 48 kHz
int16 audio is kept under OUT_DIR/rendered48k/ (pod only, never committed: it carries the speech).
Checks, in this order: GREY_CTRL must reproduce build 1 (decoded mp4 + wav/tsv bytes, D-087 rebuild
identity) -> the D-085 qc rows (refclips_qc85.run_qc: video identity vs GREY_CTRL) -> the speech rows
(speech gate, SPK integer span QC; envelope descriptive). A QC failure: final STOP to the owner
(STOP_NOTE.md, exit 1, no manifest; the speech control is reported as failed per D-089 on_final_stop).
A code exception is NOT a QC result (traceback, no STOP note): a human looks. Pass: qc.json and
speech_partial_manifest.json (shas, rates per clip, selection + corpus sha; no text).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from yct.config import load_config  # noqa: E402
from yct.tribe_run import refclips58 as R  # noqa: E402,N812
from yct.tribe_run import refclips_qc85 as Q  # noqa: E402,N812
from yct.tribe_run import speech_build as B  # noqa: E402,N812
from yct.tribe_run import speech_corpus as S  # noqa: E402,N812


def _builder():
    spec = importlib.util.spec_from_file_location("refclips_build", ROOT / "scripts" / "refclips_build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def preconditions(cfg: dict) -> dict:
    S.speech_build_preconditions(cfg)
    Q.require_frozen(cfg)
    B.require_d089(cfg)
    sel = B.check_selection_record(cfg, ROOT)
    v1 = json.loads((ROOT / cfg["controls"]["refclips_d089"]["spk_rate_rule"]["source"]).read_text())
    S.check_no_carry_over(sel, v1)
    S.build_rates(cfg, sel)
    return sel


def _stop(out: Path, why: list[str]) -> int:
    (out / "STOP_NOTE.md").write_text(
        "# p4b_ref/v2 speech build (D-085 part 2 step 4): final STOP to the owner\n"
        "The speech control is reported as FAILED (D-089 on_final_stop); every analysis that needs it is "
        "dropped and named in the report. No amendment.\n" + "".join(f"- {w}\n" for w in why))
    print(f"STOP: {why}", flush=True)
    return 1


def build_and_qc(cfg: dict, sel: dict, sel_t: dict, prov, out: Path, clips: list, verified: dict,
                 check_build1: bool = True, rb=None) -> tuple[int, dict]:
    """Build every clip, then the checks in order; returns (exit code, qc result or {})."""
    rb = rb or _builder()
    B.utterance_map([c for c in clips if c.family in R.AUDIO], sel_t)
    out.mkdir(parents=True, exist_ok=True)
    r48 = out / "rendered48k"
    r48.mkdir(exist_ok=True)
    recs, rendered = {}, {}
    for c in clips:
        audio, rows = R.clip_audio(c, prov if c.family in R.AUDIO else None)
        shas = R.encode(R.clip_frames(c, None), audio, rows, out, c.name, cfg)
        rendered[c.name] = Q.pcm16(audio)
        R._write_wav(audio, r48 / f"{c.name}.48k.wav", R.SR)
        recs[c.name] = {"name": c.name, "family": c.family, "i": c.i, "shift": c.shift, "onsets": c.onsets,
                        "control": c.control, "events": c.events, "extra": c.extra, "sha256": shas}
        if c.family in R.AUDIO:
            recs[c.name]["speech"] = S.clip_speech_meta(c.name, c.family, cfg, sel)
        print(f"built {c.name}", flush=True)
    for name in recs:
        recs[name]["decoded_sha256"] = R.decoded_sha(out / f"{name}.mp4")
    if check_build1:
        d85 = cfg["controls"]["refclips_d085"]
        rec1 = json.loads((ROOT / d85["build1_sha_record"]).read_text())["files"]
        dec1 = json.loads((ROOT / d85["build1_decoded_sha_record"]).read_text())["files"]
        fams = ["GREY_CTRL"]
        rec1, dec1 = rb.restrict_build1(rec1, dec1, fams), rb.restrict_build1(dec1, {}, fams)
        cmp = rb.restrict_recs(recs, fams)
        mm = rb.name_set_mismatches(cmp, rec1) + rb.rebuild_mismatches(cmp, rec1, dec1)
        if mm:
            return _stop(out, [f"GREY_CTRL rebuild != build 1: {m}" for m in mm]), {}
    res = Q.run_qc(clips, out, cfg, recs, yunet=None, frames_of=lambda c: R.clip_frames(c, None))
    res["speech_rows"] = B.speech_rows(clips, rendered, prov, sel_t, cfg)
    res["code_commit"] = rb.git_head()
    res["pass"] = res["pass"] and all(r["pass"] for r in res["speech_rows"])
    B.assert_no_text(res, sel_t)
    (out / "qc.json").write_text(json.dumps(res, indent=1, default=float))
    bad = [r["name"] for r in res["rows"] if not r["pass"]] + \
        [f"{r['name']} (speech)" for r in res["speech_rows"] if not r["pass"]]
    if bad:
        return _stop(out, bad), res
    doc_path = out / "speech_partial_manifest.json"
    R.manifest(list(recs.values()), rb.toolchain(), {
        "speech_selection_sha256": cfg["controls"]["refclips_artifacts"]["speech_selection_sha256"],
        "speech_corpus_sha256": cfg["controls"]["refclips_artifacts"]["speech_corpus_sha256"],
        "engine_verified": verified, "rate_wpm_by_family": S.build_rates(cfg, sel)}, doc_path)
    doc = json.loads(doc_path.read_text())
    doc.update(partial=True, families_built=sorted({c.family for c in clips}),
               qc_sha256=hashlib.sha256((out / "qc.json").read_bytes()).hexdigest(),
               builder_blob_sha1={Path(p).name: R.git_blob_sha(Path(p)) for p in
                                  (R.__file__, B.__file__, S.__file__, __file__)})
    B.assert_no_text(doc, sel_t)
    doc_path.write_text(json.dumps(doc, indent=1, sort_keys=True, default=float))
    return 0, res


def main() -> int:
    from yct.tribe_run.espeak_engine import EspeakSynth

    if os.environ.get("AWS_DEFAULT_REGION", "eu-central-1") != "eu-central-1":
        raise SystemExit("AWS_DEFAULT_REGION must be eu-central-1 (yct resources only)")
    out = Path(sys.argv[1])
    cfg = load_config()
    sel = preconditions(cfg)
    spec = S.effective_spec(cfg)
    with tempfile.TemporaryDirectory() as d:
        dst = Path(d) / "raw.html"
        subprocess.run(["aws", "s3", "cp", "--only-show-errors", "--region", "eu-central-1",
                        spec["private_raw_s3"], str(dst)], check=True)
        raw = dst.read_bytes()
    queue = S.resolve_texts(json.loads((ROOT / spec["corpus_file"]).read_text()), raw)
    sel_t = B.reconstruct_texts(sel, queue, spk_words=int(spec["spk_words"]),
                                burst_sentences=int(spec["burst_sentences"]))
    synth = EspeakSynth(spec)                       # pin verified here, before any synthesis
    clips = [c for c in R.plan(cfg) if c.family in B.BUILD_FAMILIES]
    prov = R.make_speech_provider(S.build_raw_speech(cfg, sel_t, synth))
    rc, res = build_and_qc(cfg, sel, sel_t, prov, out, clips, synth.verified)
    print(json.dumps({"pass": rc == 0, "n_rows": len(res.get("rows", [])),
                      "n_speech_rows": len(res.get("speech_rows", []))}), flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
