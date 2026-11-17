#!/usr/bin/env bash
# Runs ON the GPU instance (started detached right after boot; Watchdog P0 #4, v2.md §3).
# Every 30 s appends "<epoch> <gpu_util%> <mem_used_MiB>" to ~/yct_heartbeat.log. The pod/sandbox
# watcher (infra/lambda_gpu.py watch) polls this file into the ledger; `reap` kills the instance when
# the lines stop for 10 min or GPU util stays < 5 % for 15 min. Usage: nohup bash gpu_heartbeat.sh &
set -u
LOG="${1:-$HOME/yct_heartbeat.log}"
while true; do
  q=$(nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ')
  util="${q%%,*}"; mem="${q##*,}"
  echo "$(date +%s) ${util:-nan} ${mem:-nan}" >> "$LOG"
  sleep 30
done
