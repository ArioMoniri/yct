# Gate G-D032 packet — T3 photometric track, atlas localisation, TRIBE known issues
Commit under review: e9b891c (+ this packet). Artifact list only (no author narrative, per v2 §2).

## Artifacts
- Protocol text: docs/prompts/v2.md (v2.3) sections "Sensitivity track T3" and "Activation localisation outputs"; ROADMAP.md "T3 and localisation (v2.3)"; DECISIONS.md D-032, D-033.
- T3 code: src/yct/normalize/photometric.py (+ config.yaml normalize.photometric); tests: tests/ (grep photometric).
- Normalisation/transcribe/confounds code: src/yct/normalize/, src/yct/transcribe/, src/yct/confounds/; tests/test_normalize*, test_transcribe*, test_confounds* (names may vary: grep).
- Atlas + features + localisation: src/yct/features/atlas.py, src/yct/features/networks.py, src/yct/interpret/localize.py; config.yaml atlases/features/localize; tests/test_atlas_loaders.py, test_atlas_networks.py, test_localize.py, tests/_atlas.py.
- TRIBE issues audit: docs/tribe_known_issues.md; BUGS.md BUG-002..004; ENHANCEMENTS.md ENH-001..003 (incl. proposal to use facebook/tribev2-subcortical as EXPLORATORY).
- Test run: `python -m pytest -q` → 151 passed in 79.69s (0:01:19)
- Known stubs: on-screen text fraction (NaN), music detection not built; WhisperX version null until first GPU run; plot greys (not hatches) unreliable vertices.

## Decision requested
GO / FIX / STOP on adopting D-032 additions (and ENH-003 subcortical-exploratory proposal) into the protocol and codebase.
