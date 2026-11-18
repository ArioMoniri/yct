# Aborted run (BUG-027)

Steps requested: bug018, real, enh002. The session container restarted after "setup OK" (00:15:46 UTC); the
driver and the container-local `lambda_gpu.py watch` reaper died with it, so no exit_code / metrics.json /
child_metrics.json were written. Instance e713f2bc6aa944c491cfc9b01b209e0a (yct-wave1p2b) kept running (last
instance heartbeat: GPU 100 %, i.e. the detached bug018 step was running) and was terminated manually by the
coordinator (ledger: terminate reason "manual", t = 1794961561). Its box-side results were lost; nothing from
this run is used. Re-run with the BUG-027 fix (orphan sweep at driver start + box dead-man switch).
