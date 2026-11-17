# DATA_DECISION (v2.2 §4) — SIGNED

**Signed by:** project owner, by explicit chat message in Claude Code session
https://claude.ai/code/session_011NAQ1mksc4Ea1mJcrGfTSd on 2026-11-17 ("i sign the data regulation with this message").
**Signature method:** chat attestation (interim). Re-sign with an SSH-signed commit once `docs/owner_signing_key.pub` exists (v2.2 §2, D-021).

The owner accepts and authorises:
1. **Platform ToS risk.** Downloading founder-posted public videos with yt-dlp may conflict with platform terms of service. Accepted for non-commercial academic research; no redistribution; downloads kept private.
2. **Legal basis (GDPR Art. 6(1)(f), Art. 89 research).** Founders' faces and voices are personal data. Processing is limited to publicly self-posted videos for scientific research.
3. **DPIA-lite.** Risks: re-identification, reputational harm from "rejected" labels. Mitigations: pseudonymous `video_id`s in every output; no founder names, company names or faces in figures/reports; labels sealed (age); access limited to the owner.
4. **Retention.** Raw videos deleted 90 days after Phase 4 completes; derived features (predictions, confounds) kept. Deletion logged in DECISIONS.md.
5. **Cross-border transfer.** Media/derived inputs may be processed on Lambda Cloud GPUs in US regions (EU→US) under Lambda's terms/DPA; EC2 pod stays in eu-central-1.
6. **Licences.** TRIBE v2 CC-BY-NC-4.0 (non-commercial only; no pitch-scoring product). Llama 3.2 Community Licence + Acceptable Use Policy accepted by the owner on Hugging Face. HCP-MMP atlas terms (non-commercial research, attribution).
7. **No redistribution** of raw videos, transcripts, or per-founder outputs.
8. **Secrets** never placed in SSM command strings, git, or logs.

STOP rule: if any use becomes commercial, or a founder requests removal, the affected data is deleted and the decision re-opened.
