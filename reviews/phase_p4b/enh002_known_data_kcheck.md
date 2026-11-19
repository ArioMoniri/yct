# D-071 (f): the frozen kernel code on the ENH-002 summary courses (pre-launch disclosure)

This is descriptive only. It changes no frozen rule, threshold or `on_fail` entry.

- **Code:** `yct.controls.kernels.evaluate`, the frozen K rules read from `controls.kernel.acceptance`. Run by `scripts/p4b_enh002_kcheck.py`.
- **Input:** `outputs/runs/wave1p2b_20261118T002855Z/enh002_latency.json`, the P0 / ENH-002 reference run on an A100-SXM4-40GB. It holds the per-event courses at lags −4…+8 on both maps.
- **Output:** `enh002_known_data_kcheck.json` (this directory).

## Why this is not a p4b_ref/v1 kernel
ENH-002 used one 120 s two-chunk clip per family, with 5 events 20 s apart and a black frame. The 5 events therefore stand in for clips, with the halves split by even/odd event index (3 selection, 2 test). Three rules cannot be computed from this data:
- **K1′** needs NAT clips.
- **K3′** needs inter-event spans; only −4…+8 windows were saved.
- **K6** needs a MOT family.

K1 has only n_test = 2 here, so its p-value cannot reach .01 by construction: with t df = 1, it would need t > 31.8. The K1 FAIL below says nothing about p4b_ref/v1, where n_test is 8–10.

## Result per rule (standardised gating map; raw enters K5)

| kernel | peak | p* | K1 | K2 | K3 | K4a | K4b | K5 | K1′ / K3′ / K6 |
|---|---|---|---|---|---|---|---|---|---|
| flash → V1_V3 (descriptive in v1) | 0.166 | +4 | FAIL (t 24.2, p 0.013, n 2) | FAIL (tail: mean lags 0–3 < 0.5·peak) | PASS (SNR 4.0) | PASS (r 0.98) | PASS (r 0.99) | FAIL (p*_raw +2, Δ 2 > 1) | n/c |
| speech → AUD (gating family SPK in v1) | 3.141 | +1 | FAIL (t 17.1, p 0.019, n 2) | PASS (crossing −1) | PASS (SNR 24.1) | PASS (r 0.98) | PASS (r 0.98) | PASS (p*_raw 0) | n/c |

## Reading
- **AUD, speech:** every rule that can be computed passes except K1, and K1 fails only because n_test = 2 (see above). The ENH-002 speech-burst response meets the timing, SNR, reliability and raw/standardised agreement rules exactly as frozen.
- **V1_V3, flash:** the black→white flash response peaks late (+4 TR on the standardised map, +2 on raw). It fails K2's tail criterion and K5's peak-lag agreement. V1_V3 and FLASH are descriptive in v1, so this gates nothing. FLASH enters only K6, which compares the MOT − MOT-STAT minus FLASH − GREY-CTRL means over lags 0–3, and a late flash peak makes K6 easier to pass, not harder. This is the late flash peak that cycle-1 Referee B3 already pointed out, and it is why v1 never takes a motion kernel from FLASH.
- **K2 window:** the window [−1, +4] was chosen knowing ENH-002 (the disclosure in D-071 (f)).
