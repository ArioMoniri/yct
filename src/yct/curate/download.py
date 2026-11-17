"""P2 media download for the primary sample (runs ON THE POD; stdlib only).

Usage (on the pod, from a repo checkout)::

    python3 -m yct.curate.download --manifest data/manifest.csv --out /work/yct/raw

Downloads every ``in_primary == True`` manifest row (qc_pass False rows too: sensitivity) with yt-dlp,
best quality (``bv*+ba/b``, merged to mp4), one at a time with polite pacing (``--sleep-requests 2
--sleep-interval 5``), up to 3 attempts per video. It never evades rate limits: on HTTP 429 or a bot
check it stops the whole run and marks the remaining rows ``not_attempted``. No cookies, proxies or
impersonation are used. Rows whose url starts with ``sealed:`` are skipped (owner action).

Writes ``<out>/raw_probe.csv`` (sha256 + ffprobe technical fields) and ``<out>/download_log.csv``
(video_id, status, error_class). Titles, descriptions and uploader names are never requested or stored
(outcome-leak risk): no info-json, no description, and only the error *class* is logged.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

PROBE_COLUMNS = [
    "video_id", "sha256", "container", "vcodec", "acodec", "width", "height", "fps", "duration_s",
    "audio_hz", "audio_channels", "bitrate_kbps", "rotation", "status",
]
LOG_COLUMNS = ["video_id", "status", "error_class"]
STOP_CLASSES = {"rate_limited", "bot_check"}          # never retried, never evaded: stop the run
PERMANENT_CLASSES = {"private", "unavailable", "restricted", "unsupported_url", "http_404", "geo_blocked"}
MAX_ATTEMPTS = 3
SKIP_SUFFIXES = (".part", ".ytdl", ".tmp", ".temp")

Runner = Callable[[list[str]], subprocess.CompletedProcess]


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)


def primary_rows(manifest: str | Path) -> list[dict[str, str]]:
    with open(manifest, newline="") as fh:
        return [r for r in csv.DictReader(fh) if str(r.get("in_primary", "")).strip().lower() == "true"]


def ytdlp_cmd(url: str, video_id: str, out: Path) -> list[str]:
    return [
        "yt-dlp", "-f", "bv*+ba/b", "--merge-output-format", "mp4",
        "--sleep-requests", "2", "--sleep-interval", "5",
        "--retries", "3", "--fragment-retries", "3",
        "--no-playlist", "--no-write-info-json", "--no-write-description", "--no-write-comments",
        "--no-write-thumbnail", "--no-write-subs", "--no-mtime", "--no-progress", "--quiet", "--no-warnings",
        "-o", str(out / f"{video_id}.%(ext)s"), "--", url,
    ]


def classify_error(stderr: str) -> str:
    s = stderr.lower()
    if "429" in s or "too many requests" in s:
        return "rate_limited"
    if "sign in to confirm" in s or "not a bot" in s or "captcha" in s:
        return "bot_check"
    if "private video" in s:
        return "private"
    if "members-only" in s or "join this channel" in s or "confirm your age" in s:
        return "restricted"
    if "not available in your country" in s or ("geo" in s and "restrict" in s):
        return "geo_blocked"
    if "unsupported url" in s:
        return "unsupported_url"
    if "http error 404" in s or "404: not found" in s:
        return "http_404"
    if "http error 403" in s or "403: forbidden" in s:
        return "http_403"
    if "unavailable" in s or "has been removed" in s or "no longer available" in s or "terminated" in s:
        return "unavailable"
    if "login" in s or "log in" in s or "authentication" in s:
        return "login_required"
    if "timed out" in s or "connection" in s or "temporary failure" in s:
        return "network"
    return "other"


def find_media(out: Path, video_id: str) -> Path | None:
    hits = [p for p in out.glob(f"{video_id}.*")
            if p.is_file() and not p.name.endswith(SKIP_SUFFIXES)
            and p.suffix not in {".csv", ".log", ".json"}]
    hits = [p for p in hits if p.name.count(".") == 1]  # drop unmerged per-format parts (id.f137.mp4)
    return sorted(hits)[0] if hits else None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _ratio(x: Any) -> float | None:
    if not x or x in ("0/0", "N/A"):
        return None
    try:
        if "/" in str(x):
            a, b = str(x).split("/")
            return float(a) / float(b) if float(b) else None
        return float(x)
    except ValueError:
        return None


def _rotation(v: dict[str, Any]) -> int:
    for sd in v.get("side_data_list") or []:
        if "rotation" in sd:
            return int(float(sd["rotation"]))
    rot = (v.get("tags") or {}).get("rotate")
    return int(float(rot)) if rot not in (None, "") else 0


def probe_fields(probe: dict[str, Any]) -> dict[str, Any]:
    streams = probe.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    a = next((s for s in streams if s.get("codec_type") == "audio"), {})
    fmt = probe.get("format") or {}
    fps = _ratio(v.get("avg_frame_rate")) or _ratio(v.get("r_frame_rate"))
    br = _ratio(fmt.get("bit_rate"))
    dur = _ratio(fmt.get("duration"))
    return {
        "vcodec": v.get("codec_name", ""), "acodec": a.get("codec_name", ""),
        "width": v.get("width", ""), "height": v.get("height", ""),
        "fps": round(fps, 3) if fps else "", "duration_s": round(dur, 3) if dur else "",
        "audio_hz": a.get("sample_rate", ""), "audio_channels": a.get("channels", ""),
        "bitrate_kbps": round(br / 1000, 1) if br else "", "rotation": _rotation(v) if v else "",
    }


def ffprobe_json(path: Path, run: Runner) -> dict[str, Any]:
    res = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    if res.returncode != 0:
        raise RuntimeError("ffprobe failed")
    data = json.loads(res.stdout)
    data.get("format", {}).pop("tags", None)  # container tags can carry a title: never kept
    return data


def download_all(rows: Iterable[dict[str, str]], out: Path, run: Runner = _run,
                 log: Callable[[str], None] = print) -> tuple[list[dict], list[dict], list[str]]:
    """Returns (probe_rows, log_rows, events)."""
    out.mkdir(parents=True, exist_ok=True)
    probes: list[dict] = []
    logs: list[dict] = []
    events: list[str] = []
    stopped: str | None = None
    for r in rows:
        vid, url = r["video_id"], r["url"].strip()
        if url.startswith("sealed:"):
            logs.append({"video_id": vid, "status": "skipped", "error_class": "sealed_url_owner_action"})
            continue
        if stopped:
            logs.append({"video_id": vid, "status": "not_attempted", "error_class": f"stopped_{stopped}"})
            continue
        media = find_media(out, vid)
        err = ""
        if media is None:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                res = run(ytdlp_cmd(url, vid, out))
                media = find_media(out, vid) if res.returncode == 0 else None
                if media is not None:
                    break
                err = classify_error(res.stderr or "") if res.returncode != 0 else "no_output_file"
                with open(out / "download_stderr.log", "a") as fh:  # pod-only diagnostics
                    fh.write(f"{vid}\tattempt{attempt}\t{err}\t{(res.stderr or '')[-400:]!r}\n")
                if err in STOP_CLASSES:
                    stopped = err
                    events.append(f"{err} at {vid}")
                    break
                if err in PERMANENT_CLASSES:
                    break
        if media is None:
            logs.append({"video_id": vid, "status": "failed", "error_class": err})
            log(f"{vid} failed {err}")
            continue
        try:
            pf = probe_fields(ffprobe_json(media, run))
            status = "ok"
        except Exception:  # noqa: BLE001 - recorded as a class, never as text
            pf, status = {}, "probe_failed"
        probes.append({"video_id": vid, "sha256": sha256_file(media), "container": media.suffix.lstrip("."),
                       **{k: pf.get(k, "") for k in PROBE_COLUMNS[3:-1]}, "status": status})
        logs.append({"video_id": vid, "status": "downloaded" if status == "ok" else "probe_failed",
                     "error_class": ""})
        log(f"{vid} ok")
    return probes, logs, events


def write_csv(path: Path, cols: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", default="data/manifest.csv")
    ap.add_argument("--out", default="/work/yct/raw")
    a = ap.parse_args(argv)
    out = Path(a.out)
    probes, logs, events = download_all(primary_rows(a.manifest), out)
    write_csv(out / "raw_probe.csv", PROBE_COLUMNS, probes)
    write_csv(out / "download_log.csv", LOG_COLUMNS, logs)
    for e in events:
        print(f"RATE-LIMIT/BOT EVENT: {e} -- run stopped, not retried")
    return 2 if events else 0


if __name__ == "__main__":
    sys.exit(main())
