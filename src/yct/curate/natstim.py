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
            known_url_hashes: set[str], batch: int = 50) -> list[dict]:
    """Fill the cpu_buffer in order; append one row per evaluated candidate. Returns the buffer rows."""
    need = cfg["controls"]["refclips_auto"]["nat"]["cpu_buffer"]
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
    return passes


def buffer_ids(log: list[dict], cfg: dict) -> list[str]:
    """The fixed buffer: the cpu passes, in log order. A short buffer (snapshot exhausted) is returned as
    is; session 0 then STOPs if it yields fewer than nat_n passes (nat_select)."""
    p = [r["t1_name"] for r in cpu_rows(log) if r["decision"] == "pass"]
    buf = cfg["controls"]["refclips_auto"]["nat"]["cpu_buffer"]
    if len(p) > buf:
        raise ra.StopError(f"{len(p)} cpu passes > cpu_buffer {buf}")
    return p


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
