"""Reference-clip upload plan (D-091; council refcampaign U3): copy, never build.

Every clip of the adapted frozen manifest is copied from where its frozen-QC-passed build left it to the
final <CLIP_ID>.{mp4,wav,tsv} names in controls.refclips_d091.upload.pod_dir, then to the private
controls.refclips.s3_root + clips/ (with .sha256 sidecars). Every sha is re-verified after each copy against
the adapted manifest (mp4, tsv, wav). Sources:
  * LOC, LOC_SCR, MOT, MOT_STAT, FLASH, GREY_CTRL: the D-087 visual build dir (pod);
  * SPK, BURST: the D-085/D-089 speech build dir (pod);
  * NAT: the T1 mp4 and 16 kHz wav (nat_tsv.t1_dir) and the D-091 NAT tsv (nat_tsv.out_dir);
  * TALKFACE: the private mirror only (controls.refclips_d085.talkface.mirror_s3 + clip/).
The tsv stem always equals the mp4 stem (the clip_id).
"""
from __future__ import annotations

VISUAL = ("LOC", "LOC_SCR", "MOT", "MOT_STAT", "FLASH", "GREY_CTRL")
SPEECH = ("SPK", "BURST")
EXTS = ("mp4", "wav", "tsv")


class UploadError(SystemExit):
    """A planning or verification failure (exit 1, a human decides)."""


def plan(adapted: dict, dirs: dict) -> list[dict]:
    """One row per (clip, ext): {"clip_id", "ext", "src_kind" ("pod" | "s3"), "src", "dst", "sha256"}.
    dirs: visual_dir, speech_dir, t1_dir, nat_tsv_dir, talkface_s3 (ends with '/'), pod_dir."""
    rows = []
    for c in adapted["clips"]:
        cid, fam, name = c["clip_id"], c["family"], c["name"]
        want = {"mp4": c["mp4_sha256"], "tsv": c["tsv_sha256"], "wav": c.get("wav_sha256")}
        for ext in EXTS:
            if not want[ext]:
                raise UploadError(f"{cid}: no {ext} sha in the adapted manifest")
            if fam in VISUAL:
                kind, src = "pod", f"{dirs['visual_dir']}/{name}.{ext}"
            elif fam in SPEECH:
                kind, src = "pod", f"{dirs['speech_dir']}/{name}.{ext}"
            elif fam == "NAT":
                t1 = c["t1_name"]
                kind, src = "pod", {"mp4": f"{dirs['t1_dir']}/{t1}.mp4",
                                    "wav": f"{dirs['t1_dir']}/audio16k/{t1}.wav",
                                    "tsv": f"{dirs['nat_tsv_dir']}/{cid}.tsv"}[ext]
            elif fam == "TALKFACE":
                kind, src = "s3", f"{dirs['talkface_s3']}clip/{name}.{ext}"
            else:
                raise UploadError(f"{cid}: unknown family {fam}")
            rows.append({"clip_id": cid, "ext": ext, "src_kind": kind, "src": src,
                         "dst": f"{dirs['pod_dir']}/{cid}.{ext}", "sha256": want[ext]})
    return rows


def verify(rows: list[dict], measured: dict[str, str], where: str) -> list[str]:
    """measured: dst file name (<CLIP_ID>.<ext>) -> sha256 after the copy. Returns the mismatches."""
    bad = []
    for r in rows:
        key = f"{r['clip_id']}.{r['ext']}"
        if measured.get(key) != r["sha256"]:
            bad.append(f"{where}:{key}")
    return bad


def record(rows: list[dict], pod_bad: list[str], s3_bad: list[str], s3_prefix: str) -> dict:
    clips: dict[str, dict] = {}
    for r in rows:
        clips.setdefault(r["clip_id"], {})[r["ext"]] = r["sha256"]
    return {"decision": "D-091", "n_clips": len(clips), "n_files": len(rows), "pod_mismatches": pod_bad,
            "s3_mismatches": s3_bad, "s3_prefix": s3_prefix, "ok": not pod_bad and not s3_bad,
            "clips": {k: clips[k] for k in sorted(clips)}}
