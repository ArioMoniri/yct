#!/usr/bin/env bash
# Generate P0 synthetic test clips + hand-made transcripts (<stem>.tsv, so TRIBE skips WhisperX).
#   smoke/smoke.mp4     10 s testsrc2 640x360@30 + espeak English sentence (16 kHz mono)
#   impulse/impulse.mp4 40 s black; full-white frames t in [15,16); 1 s speech burst at t=25; silence otherwise
#   control/control.mp4 40 s black, digital silence, empty transcript (subtract from impulse for latency)
# Word timings are approximate (uniform over the espeak utterance) — adequate for smoke/latency.
# Usage: bash make_test_clips.sh OUTDIR
set -euo pipefail
O="${1:?outdir}"; mkdir -p "$O/smoke" "$O/impulse" "$O/control"; cd "$O"
FF="ffmpeg -nostdin -hide_banner -loglevel error -y"
dur() { ffprobe -v error -show_entries format=duration -of csv=p=0 "$1"; }

# --- (a) smoke clip ---
SENT="The quick brown fox jumps over the lazy dog while the young founders explain their new company."
espeak-ng -v en-us -s 160 -w smoke/speech_raw.wav "$SENT"
$FF -i smoke/speech_raw.wav -af "aresample=16000,adelay=500:all=1,apad=whole_dur=10" -ac 1 -t 10 smoke/audio16k.wav
$FF -f lavfi -i "testsrc2=size=640x360:rate=30:duration=10" -i smoke/audio16k.wav \
    -c:v libx264 -pix_fmt yuv420p -r 30 -c:a aac -ar 16000 -ac 1 -shortest smoke/smoke.mp4
python3 - "$SENT" 0.5 "$(dur smoke/speech_raw.wav)" smoke/smoke.tsv <<'PY'
import sys
sent, t0, d, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
words = sent.split(); step = d / len(words)
with open(out, "w") as f:
    f.write("text\tstart\tduration\tsequence_id\tsentence\n")
    for i, w in enumerate(words):
        f.write(f"{w}\t{t0 + i*step:.3f}\t{step*0.9:.3f}\t0\t{sent}\n")
PY

# --- (b) impulse clip ---
BURST="Hello there."
espeak-ng -v en-us -s 200 -w impulse/burst_raw.wav "$BURST"
$FF -i impulse/burst_raw.wav -af "aresample=16000,apad,atrim=0:1,adelay=25000:all=1,apad=whole_dur=40" -ac 1 -t 40 impulse/audio16k.wav
$FF -f lavfi -i "color=c=black:size=640x360:rate=30:duration=40" -i impulse/audio16k.wav \
    -vf "drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='gte(t,15)*lt(t,16)'" \
    -c:v libx264 -pix_fmt yuv420p -r 30 -c:a aac -ar 16000 -ac 1 -t 40 impulse/impulse.mp4
python3 - "$BURST" 25.0 "$(dur impulse/burst_raw.wav)" impulse/impulse.tsv <<'PY'
import sys
sent, t0, d, out = sys.argv[1], float(sys.argv[2]), min(float(sys.argv[3]), 1.0), sys.argv[4]
words = sent.split(); step = d / len(words)
with open(out, "w") as f:
    f.write("text\tstart\tduration\tsequence_id\tsentence\n")
    for i, w in enumerate(words):
        f.write(f"{w}\t{t0 + i*step:.3f}\t{step*0.9:.3f}\t0\t{sent}\n")
PY
# --- (c) control clip ---
$FF -f lavfi -i "color=c=black:size=640x360:rate=30:duration=40" -f lavfi -i "anullsrc=r=16000:cl=mono" \
    -c:v libx264 -pix_fmt yuv420p -c:a aac -ar 16000 -ac 1 -t 40 control/control.mp4
: > control/control.tsv
rm -f smoke/speech_raw.wav smoke/audio16k.wav impulse/burst_raw.wav impulse/audio16k.wav
for c in smoke/smoke.mp4 impulse/impulse.mp4 control/control.mp4; do echo "$c $(dur $c)s $(sha256sum $c | cut -c1-16)"; done
