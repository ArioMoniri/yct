"""P3 per-TR stimulus confounds (M0) on the TRIBE 1.0 s grid."""

from yct.confounds.core import (
    FEATURES,
    apply_transcript,
    extract_confounds,
    pitch_track,
    speech_rate_summary,
    tr_grid,
    word_rate_per_tr,
)

__all__ = ["FEATURES", "apply_transcript", "extract_confounds", "pitch_track", "speech_rate_summary",
           "tr_grid",
           "word_rate_per_tr"]
