"""T-NAT0 (D-075 §3): the NAT clip pipeline. CPU stage on the yct pod, then session 0 on one Lambda GPU.

CPU stage (pod): over the frozen NAT snapshot (data/refstim/snapshots/nat_nat_snapshot.json, sha ==
controls.refclips_artifacts.nat_snapshot_sha256, frozen) in ascending sha256(title) order:
  C1   licence and personality rights as D-071 (b) (refstim.licence_of / admissible; image_licences)
  T58  Commons duration >= stimulus.t1_trim_s, else too_short (metadata, before any download)
  C4   no YC link: the frozen C4 metadata rule on title + description + categories, reason yc_link
  P2   download (owner-approved UA, sha1 == Commons sha1) + yct.normalize.normalize_video (identical to the
       analysis T1); trimmed duration >= t1_trim_s, else too_short
The first cpu_buffer (40) passes fill the fixed buffer. Rule ids T58/P2 are labels in the NAT log only;
every reason is in controls.refclips.reject_reasons. Every logged row is appended once to the frozen
controls.refclips_auto.logs.nat (append-only, stage "cpu"); a resumed run starts after the last logged row
and refuses unless the log is a prefix of the order. Fail-closed: a download/decode/normalise error is a
STOP, never a reject (D-075).
Session 0 (GPU, scripts/gpu_p4b_nat0.py) then runs N1 / N2 (refstim_auto.nat_decide), P2b and N3 over the
buffer and selects the first nat_n passes (refstim_auto.nat_select)."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from yct.curate import refstim as rs
from yct.curate import refstim_auto as ra

STAGE_CPU = "cpu"
STAGE_CPU_END = "cpu_end"     # terminal record: the snapshot was exhausted before cpu_buffer passes
CPU_RULES = {"C1": ["licence", "personality_rights"], "T58": "too_short", "C4": "yc_link", "P2": "too_short"}


def check_snapshot(cfg: dict, path: Path) -> list[dict]:
    """The frozen NAT snapshot, in sha256(title) order. Refuses unless its sha equals the frozen value and
    the frozen config row for nat_snapshot_sha256 exists."""
    want = cfg["controls"]["refclips_artifacts"]["nat_snapshot_sha256"]
    rows = {r["key"] for r in cfg.get("frozen") or []}
    if "controls.refclips_artifacts.nat_snapshot_sha256" not in rows or not want:
        raise ra.StopError("nat_snapshot_sha256 is not frozen (D-075 step 0)")
    if rs.file_sha(path) != want:
        raise ra.StopError(f"NAT snapshot sha {rs.file_sha(path)[:12]} != frozen {want[:12]}")
    snap = json.loads(path.read_text())
    h, r = snap["header"], cfg["controls"]["refclips"]
    if (h.get("kind") != "nat" or h.get("queries") != [r["nat_query"]]
            or h.get("limit") != r["snapshot_limits"]["nat"]):
        raise ra.StopError(f"NAT snapshot header {h} != config")
    return rs.ordered(snap)


def metadata_decide(title: str, meta: dict, cfg: dict, key_hashes: set[str], longest: int) -> dict:
    """C1, T58, C4 on Commons metadata only. Returns {decision: reject|continue, rule, reason, values}."""
    a = cfg["controls"]["refclips_auto"]
    lic, tmpl = rs.licence_of(meta["templates"], meta.get("license_short"))
    v = {"licence": lic, "licence_template": tmpl, "duration_s": meta.get("duration"),
         "templates_sha256": ra.templates_digest(meta["templates"])}

    def rej(rule: str, which: int = 0) -> dict:
        reasons = CPU_RULES[rule] if isinstance(CPU_RULES[rule], list) else [CPU_RULES[rule]]
        return {"decision": "reject", "rule": rule, "reason": reasons[which], "values": v}

    if tmpl == rs.PERSONALITY:
        return rej("C1", 1)
    if not rs.admissible(lic, cfg["controls"]["refclips"]["image_licences"]):
        return rej("C1", 0)
    dur = meta.get("duration")
    if dur is None:
        raise ra.StopError(f"Commons returned no duration for {title!r} (fail-closed)")
    ra.finite(float(dur))
    if float(dur) < cfg["stimulus"]["t1_trim_s"]:
        return rej("T58")
    com = a["common"]
    text = " ".join([title, meta.get("description", ""), meta.get("categories", "")])
    if ra.metadata_hit(text, com["metadata_terms"], com["metadata_regex"], key_hashes, longest):
        return rej("C4")
    return {"decision": "continue", "rule": None, "reason": None, "values": v}


def normalised_decide(rec: dict, cfg: dict) -> tuple[str | None, str | None]:
    """P2: the normalised clip must hold the full t1_trim_s after the analysis trims."""
    kept = float(rec["trimmed_duration_s"])
    ra.finite(kept)
    if kept < cfg["stimulus"]["t1_trim_s"]:
        return "P2", "too_short"
    return None, None


def load_log(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def cpu_rows(log: list[dict]) -> list[dict]:
    return [r for r in log if r.get("stage") == STAGE_CPU]


def check_prefix(done: list[dict], order: list[dict]) -> None:
    if [r["title"] for r in done] != [e["title"] for e in order[:len(done)]]:
        raise ra.StopError("NAT log is not a prefix of the sha256(title) order")


def run_cpu(order: list[dict], cfg: dict, log_path: Path, page_meta: Callable[[list[str]], dict],
            fetch_normalise: Callable[[dict, dict], dict], key_hashes: set[str], longest: int,
            known_url_hashes: set[str], batch: int = 50, n_buffers: int = 1) -> list[dict]:
    """Fill n_buffers * cpu_buffer CPU passes in order (D-084: n_buffers > 1 only via check_cpu_target);
    append one row per evaluated candidate. Returns the pass rows."""
    need = cfg["controls"]["refclips_auto"]["nat"]["cpu_buffer"] * n_buffers
    done = cpu_rows(load_log(log_path))
    check_prefix(done, order)
    passes = [r for r in done if r["decision"] == "pass"]
    i = len(done)
    while len(passes) < need and i < len(order):
        chunk = order[i:i + batch]
        meta = page_meta([e["title"] for e in chunk])
        for e in chunk:
            if len(passes) >= need:
                break
            t = e["title"]
            m = meta[t]
            row = {"stage": STAGE_CPU, "title": t, "sha256_title": rs.title_key(t), "pageid": e.get("pageid"),
                   "snapshot_revid": e.get("revid"), "read_revid": m.get("read_revid"),
                   "templates": m["templates"]}
            d = metadata_decide(t, m, cfg, key_hashes, longest)
            row.update(d)
            if d["decision"] == "continue":
                if rs.url_hash(m["url"]) in known_url_hashes:
                    raise ra.StopError(f"NAT candidate {t!r} url hash is in a wave-1/wave-2 "
                                       "manifest (D-071 c)")
                rec = fetch_normalise(e, m)       # STOP (never a reject) on any download/decode error
                rule, reason = normalised_decide(rec, cfg)
                kept = round(float(rec["trimmed_duration_s"]), 3)
                row["values"] = {**d["values"], "trimmed_duration_s": kept}
                row.update(url=m["url"], source_sha1=rec["source_sha1"], source_sha256=rec["source_sha256"],
                           t1_sha256=rec["sha256"], wav_sha256=rec.get("wav_sha256"), t1_name=rec["video_id"])
                if rule:
                    row.update(decision="reject", rule=rule, reason=reason)
                else:
                    row.update(decision="pass", rule=None, reason=None,
                               attribution=rs.attribution(m.get("artist", ""), m.get("credit", "")))
            assert row["decision"] in ("pass", "reject")
            if row["reason"] is not None and \
                    row["reason"] not in cfg["controls"]["refclips"]["reject_reasons"]:
                raise ra.StopError(f"reason {row['reason']} not in reject_reasons")
            ra.append_jsonl(log_path, row)
            i += 1
            if row["decision"] == "pass":
                passes.append(row)
    if len(passes) < need and i >= len(order) and \
            not any(r.get("stage") == STAGE_CPU_END for r in load_log(log_path)):
        ra.append_jsonl(log_path, {"stage": STAGE_CPU_END, "reason": "snapshot_exhausted", "n_evaluated": i,
                                   "n_pass": len(passes), "n_order": len(order)})
    return passes


def snapshot_exhausted(log: list[dict]) -> bool:
    """True iff the log carries the run_cpu terminal record and its counts match the logged cpu rows."""
    rows = cpu_rows(log)
    n_pass = sum(r["decision"] == "pass" for r in rows)
    return any(r.get("stage") == STAGE_CPU_END and r.get("reason") == "snapshot_exhausted"
               and r.get("n_evaluated") == len(rows) and r.get("n_pass") == n_pass for r in log)


def cpu_passes(log: list[dict]) -> list[str]:
    """t1_names of the CPU passes in log order (= snapshot order, check_prefix); index = CPU rank."""
    return [r["t1_name"] for r in cpu_rows(log) if r["decision"] == "pass"]


def buffer_complete(log: list[dict], cfg: dict, k: int = 0) -> bool:
    """Session k may launch only on a complete buffer (council D-082 W2/B1; D-084): exactly cpu_buffer passes,
    or a short LAST buffer whose CPU stage logged snapshot_exhausted."""
    n = len(buffer_ids(log, cfg, k))
    return n == cfg["controls"]["refclips_auto"]["nat"]["cpu_buffer"] or (n > 0 and snapshot_exhausted(log))


def buffer_ids(log: list[dict], cfg: dict, k: int = 0) -> list[str]:
    """Buffer k: CPU passes [k*cpu_buffer, (k+1)*cpu_buffer) in log order (k = 0 is the session-0 buffer). A
    short buffer is returned as is; the driver launches only if buffer_complete."""
    if k < 0:
        raise ra.StopError(f"buffer index {k} < 0")
    buf = cfg["controls"]["refclips_auto"]["nat"]["cpu_buffer"]
    return cpu_passes(log)[k * buf:(k + 1) * buf]


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def stream_get(url: str, dest: Path, opener=None, clock=None) -> Path:
    """rs.http_get's policy (config UA, >= min_interval_s per host, Retry-After, backoff, 429 STOP limit),
    streamed to disk (Commons videos can be large). A partial file is removed on any failure."""
    import time as _time
    import urllib.error
    import urllib.parse
    import urllib.request

    c = rs._http_cfg()
    opener = opener or urllib.request.urlopen
    clock = clock or _time
    host = urllib.parse.urlsplit(url).netloc
    req = urllib.request.Request(url, headers={"User-Agent": c["user_agent"]})
    first_429, attempt = None, 0
    tmp = dest.with_suffix(dest.suffix + ".part")
    while True:
        gap = c["min_interval_s"] - (clock.time() - rs._LAST_REQUEST.get(host, -1e18))
        if gap > 0:
            clock.sleep(gap)
        rs._LAST_REQUEST[host] = clock.time()
        try:
            with opener(req, timeout=300) as r, open(tmp, "wb") as f:
                for b in iter(lambda: r.read(1 << 20), b""):
                    f.write(b)
            tmp.replace(dest)
            return dest
        except urllib.error.HTTPError as e:
            tmp.unlink(missing_ok=True)
            if e.code not in (429, 500, 502, 503, 504):
                raise rs.CurationError(f"HTTP {e.code} for {url}") from e
            now = clock.time()
            if e.code == 429:
                first_429 = now if first_429 is None else first_429
                if now - first_429 > c["max_429_wait_s"]:
                    raise rs.CurationError(f"HTTP 429 from {host} for > {c['max_429_wait_s']} s: STOP") from e
            ra_h = e.headers.get("Retry-After") if e.headers else None
            wait = float(ra_h) if ra_h and str(ra_h).strip().isdigit() else c["backoff_base_s"] * 2 ** attempt
            attempt += 1
            clock.sleep(wait)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            tmp.unlink(missing_ok=True)
            if attempt >= 6:
                raise rs.CurationError(f"network error for {url}: {e}") from e
            clock.sleep(c["backoff_base_s"] * 2 ** attempt)
            attempt += 1


# ---------------------------------------------------------------- session 0 (GPU results -> selection)
STAGE_S0 = "session0"
STAGE_SK = "session"     # D-084 continuation rows: {"stage": "session", "session": k >= 1, ...}
N3_MIN = 0.5    # D-071 (c): face_present_crop >= 0.5 over W (unchanged by D-075)


def n3_value(face_present_crop, cfg: dict) -> float:
    """N3: mean face_present_crop over W = [window.start_tr, window.end_tr) of the P3 (yct.confounds)
    per-TR table of the trimmed T1 clip. A short or all-NaN window is a STOP (fail-closed)."""
    import numpy as np

    w = cfg["window"]
    s, e = int(w["start_tr"]), int(w["end_tr"])
    x = np.asarray(face_present_crop, dtype=float)[s:e]
    if len(x) != e - s or not np.isfinite(x).any():
        raise ra.StopError(f"face_present_crop covers {len(x)} of {e - s} W TRs (fail-closed)")
    v = float(np.nanmean(x))
    ra.finite(v)
    return v


class Session0Stop(ra.StopError):
    """Fewer than nat_n passes in the buffer: STOP to the owner. .rows = the rows to log first."""

    def __init__(self, rows: list[dict], n_pass: int):
        super().__init__(f"{n_pass} NAT passes < nat_n in the buffer: STOP to the owner")
        self.rows = rows


def session0_rows(buffer: list[str], gpu: dict[str, dict], n3: Callable[[str], float],
                  cfg: dict) -> list[dict]:
    """N1, N2 (ra.nat_decide on the session-0 outputs), then N3, in buffer order, up to the nat_n-th pass
    (ra.nat_select). gpu[id] = {lang_probs, segments}; a buffer id without output is a STOP. N3 (P3) is
    computed only for N1/N2 passes. Returns the stage-session0 rows; < nat_n passes -> Session0Stop."""
    missing = [i for i in buffer if i not in gpu]
    if missing:
        raise ra.StopError(f"session 0 returned no N1/N2 output for {missing[:5]} (fail-closed)")
    rows: list[dict] = []

    def decide(i: str) -> dict:
        d = ra.nat_decide(gpu[i]["lang_probs"], [tuple(s) for s in gpu[i]["segments"]], cfg)
        if d["decision"] == "pass":
            v = n3(i)
            d["values"]["face_present_crop_w"] = round(v, 6)
            if v < N3_MIN:
                d.update(decision="reject", rule="N3", reason="low_face_present")
        rows.append({"stage": STAGE_S0, "t1_name": i, **d})
        return d

    try:
        ra.nat_select(buffer, decide, cfg)
    except ra.StopError:
        raise Session0Stop(rows, sum(r["decision"] == "pass" for r in rows)) from None
    return rows


def session_rows(k: int, buffer: list[str], gpu: dict[str, dict], n3: Callable[[str], float],
                 cfg: dict) -> list[dict]:
    """D-084 continuation session k >= 1: N1, N2, then N3 (only for N1/N2 passes) on EVERY buffer id, in
    buffer order (no early stop at nat_n, so the selection never depends on session boundaries). A buffer id
    without output is a STOP. Returns the stage-session rows; never raises on a low pass count."""
    if k < 1:
        raise ra.StopError(f"continuation session k >= 1 required (got {k}); session 0 is session0_rows")
    missing = [i for i in buffer if i not in gpu]
    if missing:
        raise ra.StopError(f"session {k} returned no N1/N2 output for {missing[:5]} (fail-closed)")
    rows = []
    for i in buffer:
        d = ra.nat_decide(gpu[i]["lang_probs"], [tuple(s) for s in gpu[i]["segments"]], cfg)
        if d["decision"] == "pass":
            v = n3(i)
            d["values"]["face_present_crop_w"] = round(v, 6)
            if v < N3_MIN:
                d.update(decision="reject", rule="N3", reason="low_face_present")
        rows.append({"stage": STAGE_SK, "session": k, "t1_name": i, **d})
    return rows


def gpu_rows(log: list[dict]) -> list[dict]:
    """Session-0 and continuation rows (N1/N2/N3 decisions)."""
    return [r for r in log if r.get("stage") in (STAGE_S0, STAGE_SK)]


def session_of(r: dict) -> int:
    return 0 if r["stage"] == STAGE_S0 else int(r["session"])


def sessions_logged(log: list[dict]) -> list[int]:
    return sorted({session_of(r) for r in gpu_rows(log)})


def gpu_passes(log: list[dict]) -> int:
    return sum(r["decision"] == "pass" for r in gpu_rows(log))


def nat_selection(log: list[dict], cfg: dict) -> list[str]:
    """D-084: the first nat_n passes by CPU rank over every evaluated row (session 0 and k >= 1). Fail-closed:
    an id evaluated twice, an evaluated id that is not a CPU pass, or an evaluated set that is not a prefix of
    the CPU passes (a gap) is a STOP. Returns <= nat_n ids (fewer while the selection is incomplete)."""
    rank = {t: j for j, t in enumerate(cpu_passes(log))}
    seen: dict[str, dict] = {}
    for r in gpu_rows(log):
        t = r["t1_name"]
        if t in seen:
            raise ra.StopError(f"NAT candidate {t} evaluated twice (sessions {session_of(seen[t])}, "
                               f"{session_of(r)})")
        if t not in rank:
            raise ra.StopError(f"NAT candidate {t} evaluated but not a CPU pass")
        seen[t] = r
    if sorted(rank[t] for t in seen) != list(range(len(seen))):
        raise ra.StopError("evaluated NAT candidates are not a prefix of the CPU passes (a gap)")
    need = cfg["controls"]["refclips"]["nat_n"]
    return sorted((t for t, r in seen.items() if r["decision"] == "pass"), key=rank.__getitem__)[:need]


def check_cpu_target(log: list[dict], cfg: dict, n_buffers: int) -> int:
    """D-084: the CPU stage may fill n_buffers buffers only if that is at most cpu_ahead_max beyond the
    evaluated sessions, within max_sessions, and while the selection is incomplete. Returns the pass
    target."""
    d = cfg["controls"]["refclips_d084"]
    need = cfg["controls"]["refclips"]["nat_n"]
    done = sessions_logged(log)
    if n_buffers < 1:
        raise ra.StopError(f"n_buffers {n_buffers} < 1")
    if n_buffers > 1:
        if len(nat_selection(log, cfg)) >= need:
            raise ra.StopError(f"the NAT selection is complete ({need} passes): no further CPU stage")
        if n_buffers > len(done) + d["cpu_ahead_max"]:
            raise ra.StopError(f"{n_buffers} buffers is more than {d['cpu_ahead_max']} ahead of the "
                               f"{len(done)} evaluated sessions")
        if n_buffers - 1 > d["max_sessions"]:
            raise ra.StopError(f"buffer {n_buffers - 1} exceeds max_sessions {d['max_sessions']}: "
                               "STOP to the owner")
    return n_buffers * cfg["controls"]["refclips_auto"]["nat"]["cpu_buffer"]


def nat_manifest(log: list[dict], cfg: dict) -> list[dict]:
    """The NAT set: the first nat_n passes by CPU rank over all sessions (D-084), joined to their CPU rows."""
    cpu = {r["t1_name"]: r for r in cpu_rows(log) if r["decision"] == "pass"}
    g = {r["t1_name"]: r for r in gpu_rows(log)}
    sel = nat_selection(log, cfg)
    need = cfg["controls"]["refclips"]["nat_n"]
    if len(sel) != need:
        raise ra.StopError(f"{len(sel)} NAT passes logged != nat_n {need}")
    keep = ("title", "pageid", "read_revid", "url", "source_sha1", "source_sha256", "t1_name", "t1_sha256",
            "wav_sha256", "attribution")
    out = []
    for t in sel:
        c, r = cpu[t], g[t]
        out.append({**{k: c.get(k) for k in keep}, "licence": c["values"]["licence"],
                    "licence_template": c["values"]["licence_template"], "values": r["values"],
                    "session": session_of(r)})
    return out
