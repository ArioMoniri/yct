"""T-REF58 / T-STIM (D-071 (a)-(d)): the p4b_ref/v1 58 s single-chunk reference clips. Label-free.

plan(cfg) is the deterministic clip/event schedule of every family (GREY_CTRL, SPK, BURST, FLASH, TALKFACE,
LOC + LOC_SCR, MOT + MOT_STAT, NAT slots), seeded from config. render_* produce 8-bit grey frames
(640x360, mid-grey 128, stimuli inside the central 316 px square) and 48 kHz audio; build_clip() encodes
with the P2 T1 output spec (config normalize.video / normalize.audio, bit-exact flags) plus the 16 kHz mono
sidecar and the .tsv. stimulus_qc() is design_v2 §1.5, run with the real yct.confounds video code.

Interpretation (reported to the council): the white-noise bed is ONE bed seeded with BED_SEED (D-071 (a),
design_v2 §1 "visual-only clips carry the control's audio bit for bit"); per-item seeds (D-071 (b)) are used
for every other random draw (scramble phases, dot positions, grating phase).

LOC needs the curated, SHINE-processed images (T-LIC image manifest) and NAT the curated clips (T-NAT);
both enter through manifests. Speech enters through a provider (espeak-ng on the pod); this module never
synthesises speech itself, so it runs in CI.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

W, H, FPS, DUR = 640, 360, 30, 58.0
PATCH = 316
GREY = 128
SR = 48000
SR_SIDE = 16000
BED_SEED = 20261117
TARGET_LUFS = -23.0
EVENT_S = 1.0
XFADE_S = 0.010
SWITCH_AFTER_ONSET_S = 10      # LOC scramble-exemplar switch: onset_e + 10 s, outside every [o-4, o+8]
GRATING_CYCLES = 12            # cycles across the patch
GRATING_TF_HZ = 2.0            # <= 4 Hz (V-JEPA2 16 frames/s)
DOT_N, DOT_R = 120, 4
DOT_SPEED_PX_S = 40.0
_g = np.mgrid[-4:5, -4:5]
STAMP = tuple(a[(_g[0] ** 2 + _g[1] ** 2) <= 4 ** 2] for a in _g)   # disc of radius DOT_R (px offsets)
PATCH_RMS = 32.0               # = controls.refclips.shine.rms_contrast
UTTER_RANGE = {"SPK": (1.0, 1.5), "BURST": (4.0, 6.0), "TALKFACE": (1.0, 6.0)}
VISUAL = {"LOC", "LOC_SCR", "MOT", "MOT_STAT", "FLASH"}
AUDIO = {"SPK", "BURST"}
SPAN_DBFS = -40.0              # = controls.refclips_d085.speech.span_dbfs (R-11 S-23/S-24)


# ---------------------------------------------------------------- schedule
def item_seed(cfg: dict, family: str, i: int, k: int = 0) -> int:
    """D-071 (b): seed = int(sha256(f"{seeds.refclips}:{family}:{i}:{k}").hexdigest()[:8], 16)."""
    s = f"{cfg['seeds']['refclips']}:{family}:{i}:{k}"
    return int(hashlib.sha256(s.encode()).hexdigest()[:8], 16)


def shift(i: int) -> int:
    return 0 if (i // 2) % 2 == 0 else -1


def onsets(cfg: dict, i: int) -> list[float]:
    return [float(o + shift(i)) for o in cfg["controls"]["refclips"]["onsets_s"]]


@dataclass
class Clip:
    family: str
    i: int
    shift: int
    onsets: list[float]
    events: list[dict[str, Any]]
    control: str | None              # name of the matched control clip
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return f"{self.family.lower()}_{self.i:02d}"


def plan(cfg: dict) -> list[Clip]:
    rc = cfg["controls"]["refclips"]
    fam = rc["families"]
    cats = list(rc["loc_categories"])
    dirs = list(rc["mot_directions_deg"])
    out: list[Clip] = []

    def mk(f, i, events, control, **extra):
        out.append(Clip(f, i, shift(i), onsets(cfg, i), events, control, extra))

    for i in range(fam["GREY_CTRL"]):
        mk("GREY_CTRL", i, [], None)
    ctrl = "grey_ctrl_00"
    for f, n in (("SPK", fam["SPK"]), ("BURST", fam["BURST"])):
        for i in range(n):
            ev = [{"k": k, "onset": o, "utterance": 3 * i + k} for k, o in enumerate(onsets(cfg, i))]
            mk(f, i, ev, ctrl)
    for i in range(fam["FLASH"]):
        mk("FLASH", i, [{"k": k, "onset": o} for k, o in enumerate(onsets(cfg, i))], ctrl)
    for i in range(fam["TALKFACE"]):
        mk("TALKFACE", i, [{"k": k, "onset": o, "utterance": k} for k, o in enumerate(onsets(cfg, i))], ctrl)
    for i in range(fam["LOC"]):
        row = (i // 2) % 3
        ev = [{"k": k, "onset": o, "category": cats[(row + k) % 3], "image": i,
               "scramble_seed": item_seed(cfg, "LOC", i, k), "swap_seed": item_seed(cfg, "LOC_SCR", i, k)}
              for k, o in enumerate(onsets(cfg, i))]
        sw = [o + SWITCH_AFTER_ONSET_S for o in onsets(cfg, i)[:-1]]
        mk("LOC", i, ev, f"loc_scr_{i:02d}", latin_row=row, switch_s=sw)
        mk("LOC_SCR", i, [dict(e) for e in ev], None, latin_row=row, switch_s=sw, twin_of=f"loc_{i:02d}")
    for i in range(fam["MOT"]):
        pat = "dot" if (i // 4) % 2 == 0 else "grating"
        ev = [{"k": k, "onset": o, "direction_deg": dirs[(3 * (i // 2) + k) % 8]}
              for k, o in enumerate(onsets(cfg, i))]
        seed = item_seed(cfg, "MOT", i, 0)
        mk("MOT", i, ev, f"mot_stat_{i:02d}", pattern=pat, pattern_seed=seed)
        mk("MOT_STAT", i, [dict(e) for e in ev], None, pattern=pat, pattern_seed=seed, twin_of=f"mot_{i:02d}")
    for i in range(fam["NAT"]):
        mk("NAT", i, [], None, slot=True)
    return out


def windows(clip: Clip, cfg: dict) -> list[tuple[float, float]]:
    w0, w1 = cfg["controls"]["kernel"]["window_tr"]
    return [(o + w0, o + w1) for o in clip.onsets]


# ---------------------------------------------------------------- images
def phase_scramble(img: np.ndarray, seed: int) -> np.ndarray:
    """Same amplitude spectrum, seeded random phase (Hermitian, so the result is real); mean/RMS restored."""
    x = img.astype(np.float64)
    f = np.fft.fft2(x - x.mean())
    rnd = np.angle(np.fft.fft2(np.random.default_rng(seed).random(x.shape)))
    y = np.real(np.fft.ifft2(np.abs(f) * np.exp(1j * (np.angle(f) + rnd))))
    return _norm(y, x.mean(), x.std())


def _norm(p: np.ndarray, mean: float = GREY, rms: float = PATCH_RMS) -> np.ndarray:
    sd = p.std()
    return mean + (p - p.mean()) * (rms / sd if sd > 0 else 0.0)


def _frame(patch: np.ndarray | None = None, fill: int = GREY) -> np.ndarray:
    fr = np.full((H, W), fill, np.float64)
    if patch is not None:
        y0, x0 = (H - PATCH) // 2, (W - PATCH) // 2
        fr[y0:y0 + PATCH, x0:x0 + PATCH] = patch
    return fr


def _u8(f: np.ndarray) -> np.ndarray:
    return np.clip(np.rint(f), 0, 255).astype(np.uint8)


def _in_event(t: float, clip: Clip) -> int | None:
    for e in clip.events:
        if e["onset"] <= t < e["onset"] + EVENT_S:
            return e["k"]
    return None


def _segment(t: float, clip: Clip) -> int:
    """Index of the scramble exemplar shown at time t (switches at clip.extra['switch_s'])."""
    return int(sum(t >= s for s in clip.extra["switch_s"]))


def loc_frames(clip: Clip, images: dict[str, list[np.ndarray]]) -> list[np.ndarray]:
    """LOC: the intact image replaces its scramble for 1 s per event. LOC_SCR: at each onset the scramble
    swaps to a second scramble of the same exemplar for 1 s. Exemplar switches at the same times in both."""
    ev = clip.events
    intact = [_norm(images[e["category"]][e["image"]].astype(np.float64)) for e in ev]
    scr = [phase_scramble(intact[k], ev[k]["scramble_seed"]) for k in range(len(ev))]
    swp = [phase_scramble(intact[k], ev[k]["swap_seed"]) for k in range(len(ev))]
    frames = []
    for n in range(int(DUR * FPS)):
        t = n / FPS
        k = _in_event(t, clip)
        if k is not None:
            p = intact[k] if clip.family == "LOC" else swp[k]
        else:
            p = scr[min(_segment(t, clip), len(ev) - 1)]
        frames.append(_u8(_frame(p)))
    return frames


# ---------------------------------------------------------------- motion
def _dir_vec(deg: float) -> np.ndarray:
    a = np.deg2rad(deg)
    return np.array([np.cos(a), -np.sin(a)])


def mot_frames(clip: Clip) -> list[np.ndarray]:
    """A seeded pattern, static for the whole clip; in MOT it drifts coherently for 1 s per event
    (MOT_STAT never moves). Patch mean and RMS contrast are renormalised every frame."""
    rng = np.random.default_rng(clip.extra["pattern_seed"])
    yy, xx = np.mgrid[0:PATCH, 0:PATCH].astype(np.float64)
    pos = np.zeros(2)                       # cumulative displacement (px)
    moving = clip.family == "MOT"
    if clip.extra["pattern"] == "dot":
        pts = rng.random((DOT_N, 2)) * PATCH
        pol = np.where(np.arange(DOT_N) % 2 == 0, 1.0, -1.0)
        speed = DOT_SPEED_PX_S
    else:
        phase0 = rng.random() * 2 * np.pi
        ori = rng.random() * np.pi
        period = PATCH / GRATING_CYCLES
        speed = GRATING_TF_HZ * period
    frames = []
    for n in range(int(DUR * FPS)):
        t = n / FPS
        k = _in_event(t, clip)
        if moving and k is not None:
            pos = pos + _dir_vec(clip.events[k]["direction_deg"]) * speed / FPS
        if clip.extra["pattern"] == "dot":
            p = np.zeros((PATCH, PATCH))
            c = np.rint((pts + pos) % PATCH).astype(int)
            for (cx, cy), s in zip(c, pol, strict=True):
                p[(cy + STAMP[0]) % PATCH, (cx + STAMP[1]) % PATCH] = s
        else:
            u = (xx * np.cos(ori) + yy * np.sin(ori))
            shift_px = float(pos @ np.array([np.cos(ori), np.sin(ori)]))
            p = np.sin(2 * np.pi * (u - shift_px) / period + phase0)
        frames.append(_u8(_frame(_norm(p))))
    return frames


def flash_frames(clip: Clip) -> list[np.ndarray]:
    return [_u8(_frame(fill=255 if _in_event(n / FPS, clip) is not None else GREY))
            for n in range(int(DUR * FPS))]


def grey_frames() -> list[np.ndarray]:
    g = _u8(_frame())
    return [g] * int(DUR * FPS)


def talkface_frames(clip: Clip, speaking: list[tuple[float, float]]) -> list[np.ndarray]:
    """Synthetic cartoon talking face (descriptive family): mouth opens/closes at 4 Hz while speaking."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    cx, cy = W / 2, H / 2
    head = ((xx - cx) / 110) ** 2 + ((yy - cy) / 140) ** 2 <= 1
    eyes = (((xx - cx + 40) ** 2 + (yy - cy + 35) ** 2) <= 12 ** 2) | (((xx - cx - 40) ** 2
                                                                         + (yy - cy + 35) ** 2) <= 12 ** 2)
    frames = []
    for n in range(int(DUR * FPS)):
        t = n / FPS
        talk = any(a <= t < b for a, b in speaking)
        open_ = 18 if (talk and int(t * 8) % 2 == 0) else 4
        mouth = (((xx - cx) / 45) ** 2 + ((yy - cy - 60) / open_) ** 2) <= 1
        f = np.full((H, W), float(GREY))
        f[head] = 190.0
        f[eyes] = 40.0
        f[mouth] = 60.0
        frames.append(_u8(f))
    return frames


# ---------------------------------------------------------------- audio
def _biquad(b: list[float], a: list[float], x: np.ndarray) -> np.ndarray:
    from scipy.signal import lfilter

    return lfilter(b, a, x)


def k_weight(x: np.ndarray, sr: int = SR) -> np.ndarray:
    """ITU-R BS.1770-4 K-weighting (pre-filter + RLB), coefficients from the analog prototype (any sr)."""
    from math import pi, tan

    f0, g, q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    k = tan(pi * f0 / sr)
    vh = 10 ** (g / 20)
    vb = vh ** 0.4996667741545416
    a0 = 1 + k / q + k * k
    b1 = [(vh + vb * k / q + k * k) / a0, 2 * (k * k - vh) / a0, (vh - vb * k / q + k * k) / a0]
    a1 = [1.0, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0]
    f0, q = 38.13547087602444, 0.5003270373238773
    k = tan(pi * f0 / sr)
    a2 = [1.0, 2 * (k * k - 1) / (1 + k / q + k * k), (1 - k / q + k * k) / (1 + k / q + k * k)]
    b2 = [1.0, -2.0, 1.0]
    return _biquad(b2, a2, _biquad(b1, a1, x))


def integrated_lufs(x: np.ndarray, sr: int = SR) -> float:
    """BS.1770 integrated loudness, mono, 400 ms blocks / 75 % overlap, absolute and relative gates."""
    y = k_weight(np.asarray(x, np.float64), sr)
    blk, hop = int(0.4 * sr), int(0.1 * sr)
    ms = np.array([np.mean(y[s:s + blk] ** 2) for s in range(0, len(y) - blk + 1, hop)])
    lk = -0.691 + 10 * np.log10(np.maximum(ms, 1e-20))
    g = ms[lk > -70]
    rel = -0.691 + 10 * np.log10(g.mean()) - 10
    g = ms[(lk > -70) & (lk > rel)]
    return float(-0.691 + 10 * np.log10(g.mean()))


def bed(seed: int = BED_SEED) -> np.ndarray:
    """The one white-noise bed of every clip (58 s, 48 kHz), scaled to -23 LUFS integrated."""
    x = np.random.default_rng(seed).standard_normal(int(DUR * SR))
    return x * 10 ** ((TARGET_LUFS - integrated_lufs(x)) / 20)


def place_speech(base: np.ndarray, utter: np.ndarray, t0: float) -> np.ndarray:
    """Speech REPLACES the bed over its span at the bed's local RMS, with 10 ms crossfades."""
    y = base.copy()
    s0, n = int(round(t0 * SR)), len(utter)
    seg = base[s0:s0 + n]
    u = np.asarray(utter, np.float64)
    if u.std() == 0 or len(seg) != n:
        raise ValueError("utterance empty or past the clip end")
    u = u * np.sqrt(np.mean(seg ** 2) / np.mean(u ** 2))
    f = int(XFADE_S * SR)
    w = np.ones(n)
    w[:f], w[-f:] = np.linspace(0, 1, f), np.linspace(1, 0, f)
    y[s0:s0 + n] = w * u + (1 - w) * seg
    return y


# ---------------------------------------------------------------- per-clip content
# (family, utterance index) -> (48 kHz waveform, words)
SpeechProvider = Callable[[str, int], tuple[np.ndarray, list[str]]]
# raw engine output: (family, utterance index) -> (waveform at its native rate, rate, words)
RawSpeech = Callable[[str, int], tuple[np.ndarray, int, list[str]]]


def trim_to_span(x: np.ndarray, sr: int, dbfs: float = SPAN_DBFS) -> np.ndarray:
    """R-11 S-24: cut an utterance to its -40 dBFS speech span (the corpus selection span), dropping the
    engine's leading/trailing silence padding before placement. Idempotent."""
    from yct.tribe_run.speech_corpus import speech_span

    s0, s1 = speech_span(x, sr, dbfs)
    return np.asarray(x, np.float64)[s0:s1]


def resample_bandlimited(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    """R-11 S-24: polyphase (Kaiser-windowed FIR) resampling, never nearest-sample."""
    from math import gcd

    from scipy.signal import resample_poly

    if sr_in == sr_out:
        return np.asarray(x, np.float64)
    g = gcd(int(sr_in), int(sr_out))
    return resample_poly(np.asarray(x, np.float64), int(sr_out) // g, int(sr_in) // g)


def make_speech_provider(raw: RawSpeech) -> SpeechProvider:
    """Wrap an engine (espeak-ng, 22.05 kHz) as a SpeechProvider: band-limited resample to 48 kHz, then trim
    to the -40 dBFS span. The length gate, RMS match and word times then all act on the span (S-23)."""
    def prov(family: str, idx: int) -> tuple[np.ndarray, list[str]]:
        x, sr, words = raw(family, idx)
        return trim_to_span(resample_bandlimited(x, sr, SR), SR), list(words)
    return prov


def clip_audio(clip: Clip, speech: SpeechProvider | None) -> tuple[np.ndarray, list[tuple]]:
    a = bed()
    rows: list[tuple] = []
    if clip.family in AUDIO or clip.family == "TALKFACE":
        if speech is None:
            raise ValueError(f"{clip.name}: a speech provider is required")
        lo, hi = UTTER_RANGE[clip.family]
        for e in clip.events:
            wav, words = speech(clip.family, e["utterance"])
            wav = trim_to_span(wav, SR)          # S-23: length, RMS and word times on the span
            d = len(wav) / SR
            if not lo <= d <= hi:
                raise ValueError(f"{clip.name} event {e['k']}: utterance {d:.2f} s outside [{lo}, {hi}]")
            a = place_speech(a, wav, e["onset"])
            step = d / len(words)
            sent = " ".join(words)
            rows += [(wd, e["onset"] + j * step, step, e["k"], sent) for j, wd in enumerate(words)]
            e["utterance_s"] = d
    return a, rows


def clip_frames(clip: Clip, images: dict[str, list[np.ndarray]] | None) -> list[np.ndarray]:
    if clip.family in ("LOC", "LOC_SCR"):
        if images is None:
            raise ValueError("LOC needs the T-LIC image manifest")
        return loc_frames(clip, images)
    if clip.family in ("MOT", "MOT_STAT"):
        return mot_frames(clip)
    if clip.family == "FLASH":
        return flash_frames(clip)
    if clip.family == "TALKFACE":
        spans = [(e["onset"], e["onset"] + e.get("utterance_s", 1.0)) for e in clip.events]
        return talkface_frames(clip, spans)
    if clip.family == "NAT":
        raise ValueError("NAT clips come from the T-NAT manifest, not the builder")
    return grey_frames()


# ---------------------------------------------------------------- encode
FF = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]


def _write_wav(x: np.ndarray, path: Path, sr: int) -> None:
    import wave

    pcm = np.clip(np.rint(x * 32767), -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def encode(frames: list[np.ndarray], audio: np.ndarray, rows: list[tuple], out_dir: Path, name: str,
           cfg: dict) -> dict[str, str]:
    """mp4 (P2 T1 output spec, bit-exact flags) + 16 kHz mono sidecar wav + .tsv. Returns {kind: sha256}."""
    v, a = cfg["normalize"]["video"], cfg["normalize"]["audio"]
    out_dir.mkdir(parents=True, exist_ok=True)
    wav48, mp4 = out_dir / f"{name}.48k.wav", out_dir / f"{name}.mp4"
    _write_wav(audio, wav48, SR)
    cmd = [*FF, "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(wav48), "-map", "0:v", "-map", "1:a",
           "-c:v", v["codec"], "-crf", str(v["crf"]), "-preset", v["preset"], "-pix_fmt", v["pix_fmt"],
           "-threads", str(v["threads"]),
           *_color_tags(cfg),
           "-c:a", a["codec"], "-ar", str(a["sample_rate"]), "-b:a", str(a["bitrate"]),
           "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact", "-map_metadata", "-1",
           "-t", f"{DUR:.3f}", str(mp4)]
    subprocess.run(cmd, input=b"".join(f.tobytes() for f in frames), check=True)
    wav16 = out_dir / f"{name}.wav"
    subprocess.run([*FF, "-i", str(wav48), "-ar", str(SR_SIDE), "-ac", "1", "-c:a", "pcm_s16le",
                    "-fflags", "+bitexact", "-flags:a", "+bitexact", "-map_metadata", "-1", str(wav16)],
                   check=True)
    wav48.unlink()
    tsv = out_dir / f"{name}.tsv"
    with open(tsv, "w") as f:
        f.write("text\tstart\tduration\tsequence_id\tsentence\n")
        for wd, s, d, q, sent in rows:
            f.write(f"{wd}\t{s:.3f}\t{d:.3f}\t{q}\t{sent}\n")
    return {k: _sha(p) for k, p in (("mp4", mp4), ("wav", wav16), ("tsv", tsv))}


def _color_tags(cfg: dict) -> list[str]:
    """R-11 S-22: the P2 bt709/tv bitstream tags (normalize.color). Metadata only: the grey frames are not
    re-matrixed, so decoded pixels are unchanged; mp4 bytes differ from build 1 (D-086)."""
    from yct.normalize.core import color_tags

    return color_tags(cfg["normalize"]["color"])


def decoded_sha(mp4: Path) -> str:
    """sha256 of the decoded video (yuv420p raw) + audio (s16le) streams: equal decoded content <=> equal
    stimulus, independent of container/bitstream metadata such as the S-22 colour tags."""
    h = hashlib.sha256()
    for args in (["-map", "0:v:0", "-f", "rawvideo", "-pix_fmt", "yuv420p"],
                 ["-map", "0:a:0", "-f", "s16le", "-acodec", "pcm_s16le"]):
        out = subprocess.run([*FF, "-i", str(mp4), *args, "-"], capture_output=True, check=True).stdout
        h.update(hashlib.sha256(out).digest())
    return h.hexdigest()


def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def build_clip(clip: Clip, out_dir: Path, cfg: dict, images=None, speech: SpeechProvider | None = None
               ) -> dict[str, Any]:
    audio, rows = clip_audio(clip, speech)
    frames = clip_frames(clip, images)
    shas = encode(frames, audio, rows, out_dir, clip.name, cfg)
    return {"name": clip.name, "family": clip.family, "i": clip.i, "shift": clip.shift, "onsets": clip.onsets,
            "control": clip.control, "events": clip.events, "extra": clip.extra, "sha256": shas}


def git_blob_sha(path: Path) -> str:
    """The git blob sha1 of a file (as `git hash-object`), recorded for every builder script (D-071 (b))."""
    data = Path(path).read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def manifest(records: list[dict], toolchain: dict[str, str], sources: dict[str, str], path: Path) -> str:
    """refclips_manifest.json (D-071 (d)); returns its sha256, which goes to
    controls.refclips_artifacts.manifest_sha256."""
    doc = {"version": "p4b_ref/v1", "clips": sorted(records, key=lambda r: r["name"]), "toolchain": toolchain,
           "sources": sources, "builder_blob_sha1": {Path(__file__).name: git_blob_sha(Path(__file__))}}
    text = json.dumps(doc, indent=1, sort_keys=True, default=float)
    Path(path).write_text(text)
    return hashlib.sha256(text.encode()).hexdigest()


# ---------------------------------------------------------------- §1.5 stimulus QC (real confounds code)
def stimulus_qc(clip: Clip, mp4: Path, cfg: dict, twin: tuple[Clip, Path] | None = None) -> dict[str, Any]:
    """design_v2 §1.5 / D-071 (a), on the built clip with yct.confounds.video_features:
    LOC face events: face cascade on >= 90 % of face-event TRs; face_area_crop_frac == 0 on every other LOC
    TR and on every LOC_SCR TR; MOT: motion_energy_crop over event TRs >= 10x the MOT_STAT twin's."""
    from yct.confounds.core import tr_grid, video_features

    tr = cfg["tribe"]["tr_s"]
    grid = tr_grid(DUR, tr)
    vf = video_features(mp4, grid, cfg)
    ev_tr = sorted({int(e["onset"] // tr) for e in clip.events})
    if any(t >= len(grid) for t in ev_tr):
        raise ValueError(f"{clip.name}: event TR past the clip end (truncated clip)")
    res: dict[str, Any] = {"name": clip.name, "pass": True, "checks": {}}
    if clip.family in ("LOC", "LOC_SCR"):
        fa = np.nan_to_num(vf["face_area_crop_frac"])
        face_tr = ([int(e["onset"] // tr) for e in clip.events if e["category"] == "face"]
                   if clip.family == "LOC" else [])
        hit = float(np.mean(fa[face_tr] > 0)) if face_tr else None
        other = np.ones(len(fa), bool)
        other[face_tr] = False
        clean = bool(np.all(fa[other] == 0))
        res["checks"] = {"face_hit_frac": hit, "no_face_elsewhere": clean}
        res["pass"] = clean and (hit is None or hit >= 0.9)
    elif clip.family == "MOT":
        if twin is None:
            raise ValueError("MOT QC needs its MOT_STAT twin")
        vs = video_features(twin[1], grid, cfg)
        m = float(np.nanmean(vf["motion_energy_crop"][ev_tr]))
        s = float(np.nanmean(vs["motion_energy_crop"][ev_tr]))
        ratio = m / s if s > 0 else float("inf")
        res["checks"] = {"motion_event": m, "motion_static": s, "ratio": ratio}
        res["pass"] = ratio >= 10.0
    return res
