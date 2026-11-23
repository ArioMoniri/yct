"""Full p4b_ref/v1 clip manifest (D-071 (d)): assembled from the committed, frozen-QC-passed parts.

Parts:
- the visual build (outputs/runs/refclips_v2_build, D-087);
- the speech build (outputs/runs/speech_build_v2, D-085 part 2 / D-089);
- the 15 NAT rows (data/refstim/nat_manifest.json, frozen sha) and the pod dry-run record
  (outputs/runs/nat_clips_dryrun);
- the TALKFACE finish record (D-090).
Every family must be present at its frozen count (controls.refclips.families). Each part's QC must have
passed and match the qc_sha256 in its partial manifest. GREY_CTRL, built by both the visual and the speech
build, must be identical in both. NAT PD rows carry the BUG-048 concrete template next to the frozen field.
The sha256 of manifest_text() goes to controls.refclips_artifacts.manifest_sha256 (set, then frozen in the
next commit; not here).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

VISUAL = Path("outputs/runs/refclips_v2_build")
SPEECH = Path("outputs/runs/speech_build_v2")
NAT_MAN = Path("data/refstim/nat_manifest.json")
NAT_LOG = Path("data/refstim/nat_auto_log.jsonl")
NAT_DRY = Path("outputs/runs/nat_clips_dryrun/record.json")
NAT_KEY = "controls.refclips_artifacts.nat_manifest_sha256"


class ManifestError(SystemExit):
    """The full clip manifest cannot be assembled (fail-closed)."""


def _sha_text(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def concrete_pd_template(templates: list[str]) -> str | None:
    """BUG-048: the first Template:PD-… that is not the generic PD-Layout helper and not a /subpage."""
    for t in templates:
        if t.startswith("Template:PD-") and t != "Template:PD-Layout" and "/" not in t:
            return t
    return None


def load_parts(root: Path, cfg: dict) -> dict:
    """Read every committed part (no network)."""
    j = lambda p: json.loads((root / p).read_text())  # noqa: E731
    log = [json.loads(x) for x in (root / NAT_LOG).read_text().splitlines() if x.strip()]
    templates = {r["t1_name"]: r.get("templates", []) for r in log
                 if r.get("stage") == "cpu" and r.get("t1_name")}
    return {"visual": j(VISUAL / "refclips_partial_manifest.json"), "visual_qc": j(VISUAL / "qc.json"),
            "visual_qc_sha256": _sha_text(root / VISUAL / "qc.json"),
            "speech": j(SPEECH / "speech_partial_manifest.json"), "speech_qc": j(SPEECH / "qc.json"),
            "speech_qc_sha256": _sha_text(root / SPEECH / "qc.json"),
            "nat": j(NAT_MAN), "nat_sha256": _sha_text(root / NAT_MAN), "nat_dry": j(NAT_DRY),
            "nat_templates": templates}


def _check_part(name: str, part: dict, qc: dict, qc_sha: str) -> None:
    if qc.get("pass") is not True:
        raise ManifestError(f"{name}: frozen QC did not pass")
    if part.get("qc_sha256") != qc_sha:
        raise ManifestError(f"{name}: qc_sha256 in the partial manifest != sha256 of its qc.json")


def _frozen(cfg: dict, key: str) -> bool:
    return any(r["key"] == key for r in cfg.get("frozen", []))


def assemble(parts: dict, talkface: dict | None, cfg: dict) -> dict:
    fam = cfg["controls"]["refclips"]["families"]
    art = cfg["controls"]["refclips_artifacts"]
    if not _frozen(cfg, NAT_KEY) or art.get("nat_manifest_sha256") is None:
        raise ManifestError("nat_manifest_sha256 is not set and frozen")
    if parts["nat_sha256"] != art["nat_manifest_sha256"]:
        raise ManifestError("NAT manifest sha256 != the frozen nat_manifest_sha256")
    _check_part("visual", parts["visual"], parts["visual_qc"], parts["visual_qc_sha256"])
    _check_part("speech", parts["speech"], parts["speech_qc"], parts["speech_qc_sha256"])
    dry = parts["nat_dry"]
    if dry.get("manifest_sha256") != parts["nat_sha256"]:
        raise ManifestError("NAT dry run was made on a different NAT manifest")
    if dry.get("ok") is not True or dry.get("problems"):
        raise ManifestError(f"NAT dry run reported problems: {dry.get('problems')}")
    if talkface is None:
        raise ManifestError("TALKFACE finish record missing: the TALKFACE clip is not built yet")
    if (talkface.get("qc") or {}).get("pass") is not True:
        raise ManifestError("TALKFACE frozen QC did not pass")

    clips: dict[str, dict] = {}
    for part in (parts["visual"], parts["speech"]):
        for c in part["clips"]:
            prev = clips.get(c["name"])
            if prev is not None:
                if c["family"] != "GREY_CTRL" or prev["sha256"] != c["sha256"] or \
                        prev.get("decoded_sha256") != c.get("decoded_sha256"):
                    raise ManifestError(f"{c['name']}: built twice with different bytes (GREY_CTRL mismatch)")
                continue
            clips[c["name"]] = c
    rows = {r["t1_name"]: r for r in dry["rows"]}
    for i, r in enumerate(parts["nat"]):
        d = rows.get(r["t1_name"])
        if d is None or len(d.get("transcript_sha256", [])) != 1:
            raise ManifestError(f"NAT {r['t1_name']}: dry-run row or its single transcript missing")
        entry = {"name": f"nat_{i:02d}", "family": "NAT", "i": i, "events": [], "onsets": [],
                 "t1_name": r["t1_name"], "session": r["session"], "licence": r["licence"],
                 "licence_template": r["licence_template"],
                 "sha256": {"mp4": r["t1_sha256"], "wav": r["wav_sha256"],
                            "transcript": d["transcript_sha256"][0]}}
        if r["licence"] == "PD-*":
            conc = concrete_pd_template(parts["nat_templates"].get(r["t1_name"], []))
            if conc is None:
                raise ManifestError(f"NAT {r['t1_name']}: no concrete PD template in the logged templates")
            entry["licence_template_concrete"] = conc
        clips[entry["name"]] = entry
    clips["talkface_00"] = {"name": "talkface_00", "family": "TALKFACE", "i": 0, "publish": False,
                            "sha256": dict(talkface["sha256"]),
                            "decoded_sha256": talkface.get("decoded_sha256"),
                            "n_frames": talkface.get("n_frames"),
                            "frames_sha256": talkface.get("frames_sha256")}
    counts = {f: sum(c["family"] == f for c in clips.values()) for f in fam}
    if counts != fam:
        raise ManifestError(f"family counts {counts} != frozen {fam}")
    v, s = parts["visual"], parts["speech"]
    sources = {**v.get("sources", {}), **s.get("sources", {}), "nat_manifest_sha256": parts["nat_sha256"],
               "nat_dry_run_sha256": hashlib.sha256(json.dumps(dry, sort_keys=True).encode()).hexdigest(),
               "image_manifest_sha256": art.get("image_manifest_sha256"),
               "visual_qc_sha256": parts["visual_qc_sha256"], "speech_qc_sha256": parts["speech_qc_sha256"],
               "talkface_qc_pass": True}
    if v.get("toolchain") != s.get("toolchain"):
        raise ManifestError("visual and speech builds used different toolchains")
    return {"version": "p4b_ref/v1", "clips": sorted(clips.values(), key=lambda c: c["name"]),
            "toolchain": v["toolchain"], "sources": sources,
            "builder_blob_sha1": {**v.get("builder_blob_sha1", {}), **s.get("builder_blob_sha1", {})}}


def manifest_text(doc: dict) -> str:
    return json.dumps(doc, indent=1, sort_keys=True, default=float)
