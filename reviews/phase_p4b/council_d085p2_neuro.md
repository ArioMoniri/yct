# Council D-085 part 2: neuro

Verdict: **REVISE**. The work is sound. Fix the items below in the part-2 entry before it is frozen. Outcome-blind: I read no sealed data, labels, transcripts, Harvard texts or predictions.

1. **T-ENV filter: acceptable. Disclose it; no amendment.** A 10 Hz low-pass suits a syllabic envelope (energy at 2-8 Hz), and Butterworth is the standard choice. It was pinned before any corpus audio existed, and the envelope never gates. The entry must say four things:
   - `tenv` was frozen at 62c3806, before the council ratified it;
   - sosfiltfilt makes the effective order 8, with zero phase;
   - the cutoff is -6 dB at 10 Hz, not -3 dB;
   - from now on, any change needs a new decision.
2. **espeak-ng 1.51 pin: ratified.** The binary, lib and data-tree shas, plus the determinism check, are enough for formant synthesis. Two conditions:
   - synthesis re-hashes all three and fails closed on a mismatch;
   - the 22050 Hz to 16 kHz resample step and its parameters are named, being the same code path as the sidecar.
3. **Wav2Lip weights: (a), `Wav2Lip-SD-NOGAN.pt`, from the README-linked official folder.** This is closest to the council's choice: the non-GAN "accurate lip-sync" model, where mouth timing is the construct.
   - Prefer extracting the state_dict from the TorchScript archive and loading it into the pinned `models/wav2lip.py` class with `strict=True`. The pinned forward pass and preprocessing then stay unchanged.
   - Use a pure `torch.jit.load` wrapper only if the strict load fails, and record why.
   - Test on a synthetic fixture: 96x96 face and 80x16 mel give the expected output shape.
   - Freeze the loader's blob sha.
   - Disclose the May 2023 file and the deviation from `wav2lip.pth`.
   - Reject (b): it moves every pinned code path. Reject (c): its provenance is unknown.
   - Ruled on availability and provenance only, with no output seen. Ruled the same way under every choice.
4. **TALKFACE face: part 2 must name it.** D-087's continuation is scoped to `changes: [loc_image_set]` and its screen to body and place, so it does not cover a TALKFACE purpose. The part-2 entry adds `talkface.face_continuation` with these terms:
   - the v4 face log and the same frozen rules (`--target face=21`, then one more pass per skip);
   - append-only, with the existing rows byte-identical and committed before use;
   - its own a-priori cap of 20 extra passes, not drawn from the D-087 face budget;
   - cap reached or snapshot exhausted is a STOP to the owner.
5. **Freeze order: amend it.** `face_rule.skip_on` includes `wav2lip_error`, so the weights and loader must be frozen before any face candidate is tried. They are already downloaded and hashed. Order:
   1. part-2 keys, including `weights_file=Wav2Lip-SD-NOGAN.pt`, `weights_sha256`, the loader blob, `face_continuation` and `engine_pin`;
   2. corpus sha;
   3. text fetch and verify, then `select`, then `pass_rates` (exhaustion is a STOP);
   4. TALKFACE face continuation;
   5. SPK/BURST/TALKFACE build and frozen QC;
   6. clip manifest sha.

   I confirm Q4: nothing is synthesised or selected before step 2.

Blocking: items 3 and 5 (weights and loader frozen in the part-2 keys; order amended), item 4 (`face_continuation` key), and the item 1 disclosure text.
Feasibility (as already disclosed): if fewer than 60 SPK items pass of the 410, that is a STOP to the owner. Never relax the span gate after selection.
Owner questions: none. The weights source is a council matter; the licence is the same README, non-commercial and internal.

## Re-sign-off (v2: d7692c7, cadb82d, ff0bc9f)

Verdict: **REVISE**, one small blocking item. Read only v2, the response matrix, the commits and `outputs/runs/d085p2_loader_check/`. The 38 part-2 tests pass.
- Item 3: accepted. (b) does not exist (master = bac9a81, no SD loader in 113 commits), so my pre-stated fallback (a) applies. It used the strongest form: 352/352 keys, strict load into the pinned `models.Wav2Lip`, max |diff| 0.0 against the jit forward, no jit fallback, GAN refused. The deviation from `wav2lip.pth` and the May 2023 file are disclosed.
- **Blocking (items 3 and 5):** `talkface.loader` names the module, but the loader's blob sha that I asked to freeze is missing. Add `loader.blob_sha1` (currently `git hash-object` = 43f805e8…) and the sha256 of `loader_check.json` to the part-2 keys, frozen in that commit as was done for T-ENV `blob_sha1`.
- Item 1: the §1 text has all four points. The §6 entry must paste §1 in full, not only cite "§1", and must say that silent input gives zeros. I treat this as a drafting condition, not a new item.
- Item 2: accepted. The fail-closed re-hash is tested. Resampling 22050 to 48 kHz with `resample_bandlimited` makes the selection span the same quantity as the build's span.
- Items 4 and 5: accepted (`face_continuation` terms as ruled, `assert_byte_prefix`, the order). Once the blob key is added, the order holds: weights and loader are frozen before any face candidate.

## Final sign-off (v2 addendum §7: 4dedd87, 746e0c5)

- Loader keys: `talkface.loader.blob_sha1` = 43f805e8e1a3066ca138251a47aea814639fdc3b, which matches `git hash-object src/yct/tribe_run/wav2lip_loader.py`. `check_record_sha256` = d4e7d038…898a, which matches `sha256sum` of `loader_check.json`. Both are schema-typed and checked by a test; 51 tests pass. The weights and loader are frozen before any face candidate, so item 5's order holds.
- T-ENV: §6 pastes §1 word for word. That covers all four points and the statement that silent input (SD 0) gives zeros. The drafting condition is met. Nothing else is open.
APPROVE
