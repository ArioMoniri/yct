# Phase 1 gate packet (artifact list only) — wave 1 curation
Commit: 536e816. Wave-1 manifest sha256 719080c8d74f235a65bdb03f80a7d410ca25164497ef55e5e145387fbf1e61ea (D-045).
- data/manifest.csv (analyst view; 661 rows; in_primary = conf-A), data/curation/{search_log.csv, exclusions.csv, curation_report.md}
- Sealed (encrypted to owner; reviewers cannot read): data/sealed/sealed_p1.tar.age, sealed_p1b_part1.tar.age (+ .sha256)
- Counts reported by Curator (orchestrator-visible totals only): conf-A 30 accepted / 28 rejected cumulative; FireJet = 4 rejected cycles same team; C rows (556) excluded; B rows sensitivity only.
- Incidents/decisions: BUG-005, BUG-012, BUG-013, D-029 (closed), D-035, D-040, D-043, D-044, D-045.
- Pending owner action: 10-row label spot-check (decrypt locally).
ROADMAP P1 DoD: ≥20 conf-A/group; MDE recorded; fresh-agent re-derivation of 15% labels (κ≥0.9) — NOTE reviewers cannot see labels; propose how to satisfy this blind (e.g., owner-run check or sealed re-derivation agent); human spot-check 10 rows.
