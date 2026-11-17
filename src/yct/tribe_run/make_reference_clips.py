"""ENH-002 dry-run reference clips (v2.md §5 P4b; config controls.dry_run): synthetic, label-free.

  ref_control.mp4  120 s black frame + a fixed low-level white-noise bed, no words (header-only .tsv)
  ref_flash.mp4    = ref_control + 5 full-frame white flashes of 1 s at FLASH_ONSETS
  ref_speech.mp4   = ref_control + 5 espeak-ng speech bursts (4-6 s) at SPEECH_ONSETS (+ exact-time .tsv)
  ref_face.mp4     58 s synthetic cartoon talking face (skin ellipse, eyes, mouth that opens/closes at 4 Hz
                   while speaking) + continuous espeak speech on the same bed (+ .tsv). No real face footage
                   is used (none is available label-free); this is a weak face stimulus by construction.

Events are 20 s apart so each control-subtracted response window (output lags -4..+8 TR) holds one event.
The noise bed is identical (seeded) in every clip, so ref_X - ref_control isolates the event. Stdlib + ffmpeg
+ espeak-ng only (runs on the GPU box with the system python). Usage: python make_reference_clips.py OUTDIR
Prints a JSON record (onsets, durations, word counts) that the latency analysis reads (enh002.json).
"""
from __future__ import annotations

import json
import random
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

RATE = 16000
DUR = 120.0
FACE_DUR = 58.0
FLASH_ONSETS = [15.0, 35.0, 55.0, 75.0, 95.0]
SPEECH_ONSETS = [15.0, 35.0, 55.0, 75.0, 95.0]
BED_AMP = 0.01       # white-noise bed, ~ -43 dBFS RMS
SPEECH_GAIN = 0.8
SEED = 20261117
SENTENCES = [
    "Our product helps small teams ship software faster and with fewer mistakes.",
    "We started last year and already have thousands of happy customers.",
    "The market is large and growing quickly every single month.",
    "Our team has built similar systems at large companies before.",
    "Customers tell us they save hours every week using our tool.",
]
FF = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]


def _espeak(text: str, td: Path, i: int) -> tuple[list[float], float]:
    w = td / f"s{i}.wav"
    subprocess.run(["espeak-ng", "-v", "en-us", "-s", "160", "-w", str(w), text], check=True)
    with wave.open(str(w)) as f:
        assert f.getnchannels() == 1 and f.getsampwidth() == 2
        sr, n = f.getframerate(), f.getnframes()
        x = struct.unpack(f"<{n}h", f.readframes(n))
    step = sr / RATE  # nearest-sample resample to 16 kHz (espeak is 22.05 kHz)
    y = [x[int(k * step)] / 32768.0 for k in range(int(n / step))]
    return y, len(y) / RATE


def _bed(dur: float) -> list[float]:
    rng = random.Random(SEED)
    return [rng.uniform(-1.0, 1.0) * BED_AMP * 1.732 for _ in range(int(dur * RATE))]


def _write_wav(x: list[float], path: Path) -> None:
    pcm = b"".join(struct.pack("<h", max(-32767, min(32767, int(v * 32767)))) for v in x)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(pcm)


def _tsv(rows: list[tuple], path: Path) -> None:
    with open(path, "w") as f:
        f.write("text\tstart\tduration\tsequence_id\tsentence\n")
        for wd, s, d, q, sent in rows:
            f.write(f"{wd}\t{s:.3f}\t{d:.3f}\t{q}\t{sent}\n")


def _place(audio: list[float], y: list[float], t0: float) -> None:
    o = int(t0 * RATE)
    for k, v in enumerate(y[: max(0, len(audio) - o)]):
        audio[o + k] += SPEECH_GAIN * v


def _words(sent: str, t0: float, d: float, q: int) -> list[tuple]:
    words = sent.split()
    step = d / len(words)
    return [(w, t0 + k * step, step * 0.9, q, sent) for k, w in enumerate(words)]


def _mux(vf_input: list[str], vf: str | None, wav: Path, dur: float, out: Path) -> None:
    cmd = [*FF, *vf_input, "-i", str(wav)]
    if vf:
        cmd += ["-vf", vf]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-ar", "16000", "-ac", "1",
            "-t", str(dur), str(out)]
    subprocess.run(cmd, check=True)


def build(outdir: Path) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    black = ["-f", "lavfi", "-i", f"color=c=black:size=640x360:rate=30:duration={DUR}"]
    rec: dict = {"seed": SEED, "bed_amp": BED_AMP, "clips": {}}
    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        bed = _bed(DUR)
        _write_wav(bed, td / "bed.wav")
        # control + flash share the identical bed
        for name, vf in (("ref_control", None),
                         ("ref_flash", "drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='"
                          + "+".join(f"between(t,{t:g},{t + 1 - 1e-3:g})" for t in FLASH_ONSETS) + "'")):
            d = outdir / name
            d.mkdir(exist_ok=True)
            _mux(black, vf, td / "bed.wav", DUR, d / f"{name}.mp4")
            _tsv([], d / f"{name}.tsv")
            rec["clips"][name] = {"duration_s": DUR, "n_words": 0,
                                  "event_onsets_s": FLASH_ONSETS if name == "ref_flash" else []}
        # speech bursts on the bed
        audio, rows, durs = list(bed), [], []
        for i, (t0, sent) in enumerate(zip(SPEECH_ONSETS, SENTENCES, strict=True)):
            y, d = _espeak(sent, td, i)
            _place(audio, y, t0)
            rows += _words(sent, t0, d, i)
            durs.append(round(d, 3))
        _write_wav(audio, td / "speech.wav")
        d = outdir / "ref_speech"
        d.mkdir(exist_ok=True)
        _mux(black, None, td / "speech.wav", DUR, d / "ref_speech.mp4")
        _tsv(rows, d / "ref_speech.tsv")
        rec["clips"]["ref_speech"] = {"duration_s": DUR, "n_words": len(rows),
                                      "event_onsets_s": SPEECH_ONSETS, "burst_durations_s": durs}
        # talking face: continuous speech, mouth animated while speaking
        audio, rows, spans, cur, i = _bed(FACE_DUR), [], [], 1.0, 0
        while True:
            sent = SENTENCES[i % len(SENTENCES)]
            y, dd = _espeak(sent, td, 100 + i)
            if cur + dd > FACE_DUR - 1.0:
                break
            _place(audio, y, cur)
            rows += _words(sent, cur, dd, i)
            spans.append((round(cur, 3), round(cur + dd, 3)))
            cur += dd + 0.6
            i += 1
        _write_wav(audio, td / "face.wav")
        speaking = "+".join(f"between(t,{a:g},{b:g})" for a, b in spans)
        head = ("geq=r='if(lt(pow((X-320)/95,2)+pow((Y-180)/125,2),1),225,40)':"
                "g='if(lt(pow((X-320)/95,2)+pow((Y-180)/125,2),1),185,40)':"
                "b='if(lt(pow((X-320)/95,2)+pow((Y-180)/125,2),1),155,40)'")
        vf = ",".join([
            head,
            "drawbox=x=278:y=135:w=26:h=14:color=0x202020:t=fill",
            "drawbox=x=336:y=135:w=26:h=14:color=0x202020:t=fill",
            "drawbox=x=315:y=165:w=10:h=35:color=0xb08070:t=fill",
            "drawbox=x=292:y=238:w=56:h=6:color=0x501010:t=fill",
            f"drawbox=x=292:y=228:w=56:h=26:color=0x501010:t=fill:enable='({speaking})*gt(sin(2*PI*4*t),0)'",
        ])
        d = outdir / "ref_face"
        d.mkdir(exist_ok=True)
        _mux(["-f", "lavfi", "-i", f"color=c=black:size=640x360:rate=30:duration={FACE_DUR}"], vf,
             td / "face.wav", FACE_DUR, d / "ref_face.mp4")
        _tsv(rows, d / "ref_face.tsv")
        rec["clips"]["ref_face"] = {"duration_s": FACE_DUR, "n_words": len(rows), "speaking_spans_s": spans,
                                    "synthetic_cartoon_face": True}
    (outdir / "enh002.json").write_text(json.dumps(rec, indent=1))
    return rec


if __name__ == "__main__":
    print(json.dumps(build(Path(sys.argv[1]))))
