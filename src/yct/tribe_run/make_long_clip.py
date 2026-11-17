"""Long synthetic clip for the P0 chunking/windowing check (QA P0 #3, BUG-002): testsrc2 video with
espeak-ng speech throughout and our own <stem>.tsv (exact per-sentence timing, words uniform within a
sentence), so TRIBE never runs ASR. Stdlib only (runs on the GPU box before the venv exists).

Usage: python make_long_clip.py OUT.mp4 DURATION_S
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import wave
from pathlib import Path

SENTENCES = [
    "The young founders explain how their new company will change the way people work.",
    "Our product helps small teams ship software faster and with fewer mistakes.",
    "We started last year and already have thousands of happy customers.",
    "The market is large and growing quickly every single month.",
    "Our team has built similar systems at large companies before.",
    "We are raising money to hire engineers and grow our sales team.",
    "Customers tell us they save hours every week using our tool.",
    "Next year we plan to expand into three new countries in Europe.",
]
GAP_S = 0.3
FF = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]


def build(out: Path, duration: float) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    rows, frames, rate, cursor, i = [], [], None, 0.5, 0
    with tempfile.TemporaryDirectory() as td:
        while True:
            sent = SENTENCES[i % len(SENTENCES)]
            w = Path(td) / f"s{i}.wav"
            subprocess.run(["espeak-ng", "-v", "en-us", "-s", "160", "-w", str(w), sent], check=True)
            with wave.open(str(w)) as f:
                rate = rate or f.getframerate()
                assert f.getframerate() == rate and f.getnchannels() == 1
                pcm = f.readframes(f.getnframes())
                d = f.getnframes() / rate
            if cursor + d > duration - 0.5:
                break
            frames.append((cursor, pcm))
            words = sent.split()
            step = d / len(words)
            rows += [(wd, cursor + k * step, step * 0.9, 0, sent) for k, wd in enumerate(words)]
            cursor += d + GAP_S
            i += 1
        total = int(duration * rate)
        buf = bytearray(2 * total)
        for t0, pcm in frames:
            o = 2 * int(t0 * rate)
            buf[o:o + len(pcm)] = pcm[: max(0, len(buf) - o)]
        wav = Path(td) / "speech.wav"
        with wave.open(str(wav), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(rate)
            f.writeframes(bytes(buf))
        subprocess.run([*FF, "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate=30:duration={duration}",
                        "-i", str(wav), "-af", "aresample=16000", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-r", "30", "-c:a", "aac", "-ar", "16000", "-ac", "1", "-t", str(duration), str(out)],
                       check=True)
    with open(out.with_suffix(".tsv"), "w") as f:
        f.write("text\tstart\tduration\tsequence_id\tsentence\n")
        for wd, s, d, q, sent in rows:
            f.write(f"{wd}\t{s:.3f}\t{d:.3f}\t{q}\t{sent}\n")
    return {"clip": str(out), "duration_s": duration, "n_words": len(rows), "n_sentences": len(frames),
            "last_word_start_s": rows[-1][1] if rows else None}


if __name__ == "__main__":
    import json

    print(json.dumps(build(Path(sys.argv[1]), float(sys.argv[2]))))
