"""Helpers for atlas-dependent tests: load real atlases or skip cleanly when offline."""
from __future__ import annotations

import numpy as np
import pytest

from yct.features.atlas import Atlas, AtlasSet, AtlasUnavailable

NV = 20484
NH = 10242


def load_or_skip(loader):
    try:
        return loader()
    except AtlasUnavailable as e:  # offline or optional `neuro` deps missing
        pytest.skip(f"atlas unavailable: {e}")


def synthetic_atlases(seed: int = 0) -> AtlasSet:
    """Offline stand-in with real-shaped label arrays: contiguous blocks per hemisphere.

    Schaefer: 0 = medial wall (first 500 vertices of each hemi), 4 parcels/hemi (2 networks).
    """
    nets = ["Vis", "SomMot", "DorsAttn", "SalVentAttn", "Limbic", "Cont", "Default"]
    lab = np.zeros(NV, dtype=np.int64)
    names = ["Medial_Wall"]
    pid = 0
    for h, hemi in enumerate(("LH", "RH")):
        blocks = np.array_split(np.arange(h * NH + 500, (h + 1) * NH), 14)
        for i, b in enumerate(blocks):
            pid += 1
            lab[b] = pid
            names.append(f"7Networks_{hemi}_{nets[i // 2]}_{i % 2 + 1}")
    schaefer = Atlas("schaefer400_7", lab, tuple(names))
    from yct.features.atlas import yeo7_from_schaefer

    yeo = yeo7_from_schaefer(schaefer, nets)
    hcp = Atlas("hcp_mmp1", np.where(lab > 0, (lab + 1) // 2, 0),
                ("???", *[f"X_{i}_ROI" for i in range(1, 15)]))
    des = Atlas("destrieux", np.where(lab > 0, 1 + (lab - 1) % 3, 0), ("Unknown", "G_a", "G_b", "S_c"))
    return AtlasSet(schaefer=schaefer, yeo7=yeo, hcp=hcp, destrieux=des)
