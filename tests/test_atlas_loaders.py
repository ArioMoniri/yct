"""Atlas loaders on fsaverage5 (v2.md P5; tribe_requirements §3, §8). Network-dependent: marker `atlas`."""
from __future__ import annotations

import numpy as np
import pytest

from tests._atlas import NH, NV, load_or_skip
from yct.config import load_config
from yct.features import atlas as atl

pytestmark = pytest.mark.atlas


@pytest.fixture(scope="module")
def schaefer():
    return load_or_skip(atl.load_schaefer400)


def test_schaefer_shape_and_parcels(schaefer):
    assert schaefer.labels.shape == (NV,)
    assert schaefer.names[0] == atl.MEDIAL_WALL
    ids = np.unique(schaefer.labels)
    assert set(ids) == set(range(401))          # 400 parcels + medial wall, all present
    assert schaefer.n_labels == 400


def test_schaefer_hemisphere_order(schaefer):
    lh, rh = schaefer.labels[:NH], schaefer.labels[NH:]
    assert set(np.unique(lh)) - {0} == set(range(1, 201))
    assert set(np.unique(rh)) - {0} == set(range(201, 401))
    assert all("_LH_" in schaefer.names[i] for i in range(1, 201))
    assert all("_RH_" in schaefer.names[i] for i in range(201, 401))


def test_medial_wall(schaefer):
    mw = atl.schaefer_medial_wall(schaefer)
    assert mw.dtype == bool and mw.shape == (NV,)
    assert mw[:NH].sum() == 870                  # tribe_requirements §3 (checked locally there)
    assert 500 < mw[NH:].sum() < 1500
    assert (schaefer.labels[~mw] > 0).all()      # every non-medial vertex assigned a parcel


def test_yeo7_derivation(schaefer):
    yeo = atl.yeo7_from_schaefer(schaefer)
    nets = load_config()["atlases"]["yeo7"]["networks"]
    assert yeo.labels.shape == (NV,)
    assert yeo.names == (atl.MEDIAL_WALL, *nets)
    assert ((yeo.labels == 0) == atl.schaefer_medial_wall(schaefer)).all()
    for pid in (1, 57, 200, 201, 333, 400):
        net = schaefer.names[pid].split("_")[2]
        assert (yeo.labels[schaefer.labels == pid] == nets.index(net) + 1).all()
    assert set(np.unique(yeo.labels)) == set(range(8))


def test_hcp_mmp1():
    hcp = load_or_skip(atl.load_hcp_mmp1)
    assert hcp.labels.shape == (NV,) and hcp.n_labels == 360
    assert hcp.names[1].startswith("L_") and hcp.names[181].startswith("R_")
    assert hcp.labels[:NH].max() <= 180 and hcp.labels[NH:][hcp.labels[NH:] > 0].min() > 180
    for roi in ("L_FFC_ROI", "R_PH_ROI", "L_V1_ROI"):
        assert (hcp.labels == hcp.names.index(roi)).sum() > 5


def test_destrieux():
    des = load_or_skip(atl.load_destrieux)
    assert des.labels.shape == (NV,)
    assert "L Medial_wall" in des.names and "R Medial_wall" in des.names
    assert des.labels[:NH].max() <= 75 < des.labels[NH:].max()


def test_hashes_recorded_and_checked(tmp_path, monkeypatch):
    cfg = load_config()["atlases"]
    for key in ("schaefer400_7", "hcp_mmp1", "destrieux"):
        for h in ("lh", "rh"):
            assert len(cfg[key][h]["sha256"]) == 64
    p = load_or_skip(lambda: atl.atlas_file("schaefer400_7", "lh"))
    # a corrupted cache file must fail loudly, not skip
    monkeypatch.setenv("YCT_ATLAS_DIR", str(tmp_path))
    (tmp_path / p.name).write_bytes(b"corrupt")
    with pytest.raises(atl.AtlasIntegrityError):
        atl.atlas_file("schaefer400_7", "lh")


def test_offline_raises_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("YCT_ATLAS_DIR", str(tmp_path))
    monkeypatch.setattr(atl.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(atl.urllib.error.URLError("offline")))
    with pytest.raises(atl.AtlasUnavailableError):
        atl.load_schaefer400()
