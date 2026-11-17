"""Build label-free wave-1 QC + confounds summary CSVs from /work/yct/norm records (pod side).
No titles, URLs or outcome columns are read or written."""
import csv
import json
import sys
from pathlib import Path

import yaml

N, C = Path("/work/yct/norm"), Path("/work/yct/confounds")
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/work/yct/summaries")
OUT.mkdir(parents=True, exist_ok=True)
cfg = yaml.safe_load(open("/work/yct/repo/config.yaml"))
w, tr = cfg["window"], cfg["tribe"]["tr_s"]
w_end = (w["default_start_tr"] + w["default_len_tr"]) * tr
thr = w_end + w["min_tail_s"]
thr2 = w_end + 2.0

ids = [r["video_id"] for r in csv.DictReader(open("/work/yct/repo/data/manifest.csv"))
       if r["in_primary"].strip().lower() == "true"]
qc, cs = [], []
for vid in ids:
    rl = N / "runlog"
    row = {"video_id": vid}
    if (rl / f"{vid}.done").exists():
        h = (rl / f"{vid}.done").read_text().strip()
        r = json.loads((N / "records" / f"{h}.json").read_text())
        s, t = r["source"], r["trims"]
        fl = r["flags"]
        row.update(
            status="pass", fail_reason="", content_id=h,
            src_width=s.get("width"), src_height=s.get("height"),
            src_fps=s.get("fps_avg") or s.get("fps_r"), src_vcodec=s.get("video_codec"),
            src_bitrate_kbps=round((s.get("video_bitrate_bps") or s.get("bitrate_bps") or 0) / 1000, 1), src_duration_s=s.get("duration_s"),
            src_color_rule=r["color"].get("rule"), src_color_matrix=r["color"].get("in_matrix"),
            hdr_source=r["hdr_source"], aspect_ratio=round(r["aspect_ratio"], 4),
            aspect_label=r["aspect_label"], stratum_9x16=r["stratum_9x16"],
            out_width=r["out_width"], out_height=r["out_height"], upscaled=r["upscaled"],
            crop_frac_area_outside=round(r["crop_frac_area_outside"], 4),
            trim_start_s=round(t["trim_start_s"], 3), trim_end_s=round(t["trim_end_s"], 3),
            trimmed_duration_s=round(r["trimmed_duration_s"], 3), out_duration_s=round(r["out_duration_s"], 3),
            loudness_in_speech_lufs=r.get("loudness_in_speech_lufs"),
            loudness_out_speech_lufs=r.get("loudness_out_speech_lufs"),
            true_peak_out_dbtp=r.get("true_peak_out_dbtp"),
            av_offset_ms=r.get("av_offset_ms"), av_sync_flag="av_sync_offset" in fl,
            mono_phase_flag=bool(r.get("mono_phase_flag")),
            loudness_off_target="loudness_off_target" in fl,
            t3_gain_capped=bool((r.get("t3") or {}).get("gain_capped")),
            caption_flag="not_implemented",
            t1_excluded=r["trimmed_duration_s"] < thr, t1_excl_threshold_s=thr,
            t1_excluded_if_tail2s=r["trimmed_duration_s"] < thr2,
            flags=";".join(fl),
        )
    else:
        why = "missing_raw" if (rl / f"{vid}.missing").exists() else (
            "normalize_error:" + (rl / f"{vid}.failed").read_text().strip().splitlines()[-1][:160]
            if (rl / f"{vid}.failed").exists() else "not_run")
        row.update(status="fail", fail_reason=why)
    qc.append(row)
    for kind in ("t1", "t3"):
        p = C / "summary" / f"{vid}.{kind}.json"
        if p.exists():
            d = json.loads(p.read_text())
            keep = {k: v for k, v in d.items() if not isinstance(v, (list, dict))
                    and k not in ("video_id", "manifest_video_id", "text_detection")}
            cs.append({"video_id": vid, "copy": kind, **keep})

def dump(rows, path):
    cols = []
    for r in rows:
        cols += [k for k in r if k not in cols]
    with open(path, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=cols)
        wr.writeheader()
        wr.writerows(rows)

dump(qc, OUT / "wave1_normalize_qc.csv")
dump(cs, OUT / "wave1_confounds_summary.csv")
ok = [r for r in qc if r["status"] == "pass"]
print(json.dumps({
    "n_primary": len(ids), "n_pass": len(ok), "fail": {r["video_id"]: r["fail_reason"] for r in qc if r["status"] != "pass"},
    "t1_excl_threshold_s": thr, "n_t1_excluded": sum(r["t1_excluded"] for r in ok),
    "n_t1_excluded_if_tail2s": sum(r["t1_excluded_if_tail2s"] for r in ok),
    "n_hdr": sum(bool(r["hdr_source"]) for r in ok), "n_9x16": sum(bool(r["stratum_9x16"]) for r in ok),
    "n_upscaled": sum(bool(r["upscaled"]) for r in ok), "n_av_sync": sum(r["av_sync_flag"] for r in ok),
    "n_mono_phase": sum(r["mono_phase_flag"] for r in ok), "n_loud_off": sum(r["loudness_off_target"] for r in ok),
    "n_color_untagged": sum(r["src_color_rule"] != "tagged" for r in ok),
    "n_conf_t1": sum(c["copy"] == "t1" for c in cs), "n_conf_t3": sum(c["copy"] == "t3" for c in cs),
    "flag_counts": {f: sum(f in r["flags"].split(";") for r in ok)
                    for f in sorted({x for r in ok for x in r["flags"].split(";") if x})},
}, indent=1))
