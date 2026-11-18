#!/usr/bin/env bash
# Box-side dead-man switch (BUG-027). Runs ON the GPU instance, detached, next to gpu_heartbeat.sh.
# The driver touches TOUCH_FILE about once a minute (over ssh, from a thread of the driver process). If the
# touch is older than GRACE_S (driver/container died) or the box has been up longer than MAX_S (hard cap),
# the box halts itself. Lambda keeps billing a halted instance until it is TERMINATED, so this only stops the
# work; the orphan sweep (`lambda_gpu.py sweep`, run at every driver start) terminates it.
# D-063/QA P4-entry D12: optional DEADLINE_EPOCH (absolute, = the launch deadline in the instance name) also
# halts the box, so the hard cap counts from launch, not from dead-man start. The P4 driver starts this as its
# FIRST ssh command (before shipping code), and a pod-side timer terminates the instance at deadline + 15 min.
# Usage: nohup bash gpu_deadman.sh TOUCH_FILE GRACE_S MAX_S [DEADLINE_EPOCH] &   (SHUTDOWN_CMD/CHECK_S for tests)
set -u
TOUCH="${1:?touch file}"; GRACE="${2:?grace s}"; MAX="${3:?max s}"; DEADLINE="${4:-0}"
SHUTDOWN_CMD="${SHUTDOWN_CMD:-sudo shutdown -h now}"
CHECK_S="${CHECK_S:-30}"
LOG="${DEADMAN_LOG:-$HOME/yct_deadman.log}"
start=$(date +%s)
touch "$TOUCH"
while true; do
  now=$(date +%s)
  last=$(stat -c %Y "$TOUCH" 2>/dev/null || echo 0)
  if [ $((now - last)) -gt "$GRACE" ]; then
    echo "$now deadman: no driver touch for $((now - last)) s > $GRACE s -> shutdown" >> "$LOG"; $SHUTDOWN_CMD; exit 0
  fi
  if [ "$DEADLINE" -gt 0 ] && [ "$now" -gt "$DEADLINE" ]; then
    echo "$now deadman: past launch deadline $DEADLINE -> shutdown" >> "$LOG"; $SHUTDOWN_CMD; exit 0
  fi
  if [ $((now - start)) -gt "$MAX" ]; then
    echo "$now deadman: up $((now - start)) s > hard cap $MAX s -> shutdown" >> "$LOG"; $SHUTDOWN_CMD; exit 0
  fi
  sleep "$CHECK_S"
done
