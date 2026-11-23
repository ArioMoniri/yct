"""Read-only adapter over the frozen p4b_ref/v1 clip manifest (council refcampaign U1, D-091).

The frozen refclips_manifest.json (sha == controls.refclips_artifacts.manifest_sha256) stays byte-identical;
its sha is checked on the raw text BEFORE parsing (gpu_p4b_ref.load_clip_manifest). `adapt` is a pure
function from the parsed frozen schema to the driver's view:

    {"family", "i", "name", "sha256": {"mp4", "tsv"?, "wav"?, ...}, ...}  ->
    {"clip_id": FAMILY_ii, "family", "index": i, "name", "mp4_sha256", "tsv_sha256", "wav_sha256", ...}

Rules (fail closed; a missing key is a refusal, never a default):
  * clip_id = f"{family}_{i:02d}" and name.upper() == clip_id; i runs 0..n-1 in every family; ids unique;
  * the D-038 ids (GREY_CTRL_00, SPK_00, MOT_00) are present;
  * mp4/tsv shas come only from the row's sha256{} map (never transcript, never wav);
  * the 15 NAT rows carry no sha256.tsv in the frozen file: their tsv sha comes only from the D-091 sidecar
    (nat_tsv_manifest.json, its own frozen sha key), whose rows must be valid with >= 1 word; a NAT row
    that has both, or neither, is a refusal; a sidecar row for a non-NAT or unknown clip is a refusal;
  * no duration is invented here: the duration is measured on the pod (ffprobe) by the backend.
control, onsets, shift, events and twin fields pass through unchanged.
"""
from __future__ import annotations

from collections import Counter

D038_CLIPS = ("GREY_CTRL_00", "SPK_00", "MOT_00")
PASS_THROUGH = ("control", "onsets", "shift", "events", "twin_of", "publish", "session", "t1_name")


class ManifestAdapterError(SystemExit):
    """The frozen manifest cannot be read as the driver's view (exit 1, a human decides)."""


def clip_id(family: str, i: int) -> str:
    return f"{family}_{i:02d}"


def nat_tsv_index(sidecar: dict | None) -> dict[str, dict]:
    if sidecar is None:
        return {}
    rows = sidecar.get("rows")
    if not isinstance(rows, list):
        raise ManifestAdapterError("NAT tsv sidecar has no rows list")
    out: dict[str, dict] = {}
    for r in rows:
        cid = r.get("clip_id")
        if not cid or cid in out:
            raise ManifestAdapterError(f"NAT tsv sidecar: missing or duplicate clip_id {cid!r}")
        if r.get("tsv_valid") is not True or not isinstance(r.get("n_words"), int) or r["n_words"] < 1:
            raise ManifestAdapterError(f"NAT tsv sidecar: {cid} is invalid or has no words "
                                       "(STOP to the owner)")
        if not r.get("tsv_sha256"):
            raise ManifestAdapterError(f"NAT tsv sidecar: {cid} has no tsv_sha256")
        out[cid] = r
    return out


def adapt(manifest: dict, sidecar: dict | None = None) -> dict:
    clips = manifest.get("clips")
    if not isinstance(clips, list) or not clips:
        raise ManifestAdapterError("clip manifest has no clips")
    nat = nat_tsv_index(sidecar)
    out, ids, used_nat = [], [], set()
    for c in clips:
        for k in ("family", "i", "name", "sha256"):
            if k not in c:
                raise ManifestAdapterError(f"clip manifest row lacks {k!r}: {str(c)[:80]}")
        fam, i, sha = c["family"], c["i"], c["sha256"]
        if not isinstance(i, int) or not isinstance(sha, dict):
            raise ManifestAdapterError(f"clip manifest row {c['name']!r}: bad i or sha256")
        cid = clip_id(fam, i)
        if str(c["name"]).upper() != cid:
            raise ManifestAdapterError(f"clip manifest name {c['name']!r} != {cid} (name.upper() == clip_id)")
        if "mp4" not in sha:
            raise ManifestAdapterError(f"{cid}: no sha256.mp4")
        if fam == "NAT":
            if ("tsv" in sha) == (cid in nat):
                raise ManifestAdapterError(f"{cid}: the tsv sha must come from exactly one of the frozen "
                                           "manifest or the D-091 sidecar")
            tsv = sha["tsv"] if "tsv" in sha else nat[cid]["tsv_sha256"]
            used_nat.add(cid)
        else:
            if "tsv" not in sha:
                raise ManifestAdapterError(f"{cid}: no sha256.tsv")
            if cid in nat:
                raise ManifestAdapterError(f"NAT tsv sidecar names a non-NAT clip {cid}")
            tsv = sha["tsv"]
        row = {"clip_id": cid, "family": fam, "index": i, "name": c["name"], "mp4_sha256": sha["mp4"],
               "tsv_sha256": tsv, "wav_sha256": sha.get("wav")}
        row.update({k: c[k] for k in PASS_THROUGH if k in c})
        out.append(row)
        ids.append(cid)
    if len(set(ids)) != len(ids):
        raise ManifestAdapterError("clip manifest ids are not unique")
    if set(nat) - used_nat:
        raise ManifestAdapterError(f"NAT tsv sidecar names unknown clips {sorted(set(nat) - used_nat)[:3]}")
    by_fam = Counter(r["family"] for r in out)
    for fam, n in by_fam.items():
        got = sorted(r["index"] for r in out if r["family"] == fam)
        if got != list(range(n)):
            raise ManifestAdapterError(f"{fam}: indices {got[:5]}... are not 0..{n - 1}")
    missing = [d for d in D038_CLIPS if d not in ids]
    if missing:
        raise ManifestAdapterError(f"clip manifest lacks the D-038 clips {missing}")
    return {"version": manifest.get("version"), "clips": out}
