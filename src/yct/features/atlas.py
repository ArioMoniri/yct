"""Surface atlases on fsaverage5 (v2.md §5 P5; tribe_requirements §3, §8).

Every loader returns an :class:`Atlas`: a per-vertex integer label array of length 20,484
(10,242 left-hemisphere vertices followed by 10,242 right, the TRIBE output order) and a name
table indexed by label id.

* Schaefer-400 (7Net): CBIG fsaverage5 ``.annot``. Label 0 is the medial wall; LH parcels are
  1..200 and RH parcels 201..400 (the standard Schaefer numbering).
* Yeo-7: derived from the Schaefer names (``7Networks_LH_Vis_1`` -> ``Vis``); 0 = medial wall.
* HCP-MMP1: fsaverage (163,842 vertices/hemi) annot; fsaverage5 is its first 10,242 vertices per
  hemisphere, so no resampling is needed (tribe_requirements §8). 0 = ``???`` (unlabelled).
* Destrieux (a2009s): native fsaverage5 annot as fetched by nilearn. Labelling only.

Files are cached under ``atlases.cache_dir`` (env ``YCT_ATLAS_DIR`` overrides) and their sha256
is checked against ``config.yaml`` on every load. A missing file that cannot be downloaded raises
:class:`AtlasUnavailableError`; a hash mismatch raises :class:`AtlasIntegrityError`.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from yct.config import load_config

MEDIAL_WALL = "Medial_Wall"
HEMIS = ("lh", "rh")


class AtlasUnavailableError(RuntimeError):
    """The atlas file is not cached and could not be obtained (offline, missing dependency)."""


class AtlasIntegrityError(RuntimeError):
    """A cached or downloaded atlas file does not match the sha256 recorded in config.yaml."""


@dataclass(frozen=True)
class Atlas:
    name: str
    labels: np.ndarray          # (20484,) int, LH then RH
    names: tuple[str, ...]      # names[label_id]
    background: int = 0         # label id of the medial wall / unlabelled vertices

    @property
    def n_labels(self) -> int:
        """Number of non-background labels."""
        return len(self.names) - 1

    def name_of(self, label_id: int) -> str:
        return self.names[int(label_id)]


# ----------------------------------------------------------------------------- files

def _cfg(cfg: dict[str, Any] | None) -> dict[str, Any]:
    return (cfg if cfg is not None else load_config())["atlases"]


def cache_dir(cfg: dict[str, Any] | None = None) -> Path:
    env = os.environ.get("YCT_ATLAS_DIR")
    return Path(env or _cfg(cfg)["cache_dir"]).expanduser()


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path, timeout: float = 60.0) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r, tempfile.NamedTemporaryFile(
            dir=dest.parent, delete=False
        ) as tmp:
            shutil.copyfileobj(r, tmp)
            tmp_path = Path(tmp.name)
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise AtlasUnavailableError(f"cannot download {url}: {e}") from e
    tmp_path.replace(dest)


def _verified(path: Path, sha256: str) -> Path:
    got = sha256_file(path)
    if got != sha256:
        raise AtlasIntegrityError(f"{path}: sha256 {got} != expected {sha256} (config.yaml atlases)")
    return path


def atlas_file(atlas_key: str, hemi: str, cfg: dict[str, Any] | None = None) -> Path:
    """Path to a cached, hash-verified annot file; download it if missing."""
    entry = _cfg(cfg)[atlas_key][hemi]
    path = cache_dir(cfg) / entry["file"]
    if not path.exists():
        if "url" in entry:
            _download(entry["url"], path)
        elif atlas_key == "destrieux":
            _fetch_destrieux(cfg)
        if not path.exists():
            raise AtlasUnavailableError(f"{path} missing after fetch")
    return _verified(path, entry["sha256"])


def _fetch_destrieux(cfg: dict[str, Any] | None) -> None:
    try:
        from nilearn import datasets
    except ImportError as e:  # optional `neuro` group
        raise AtlasUnavailableError("nilearn is not installed (pip install -e '.[neuro]')") from e
    try:
        datasets.fetch_atlas_surf_destrieux(data_dir=str(cache_dir(cfg) / "nilearn"), verbose=0)
    except Exception as e:  # nilearn wraps network failures in several exception types
        raise AtlasUnavailableError(f"nilearn Destrieux fetch failed: {e}") from e


def _read_annot(path: Path, n: int) -> tuple[np.ndarray, list[str]]:
    try:
        import nibabel as nib
    except ImportError as e:
        raise AtlasUnavailableError("nibabel is not installed (pip install -e '.[neuro]')") from e
    labels, _ctab, names = nib.freesurfer.read_annot(str(path))
    if labels.shape[0] < n:
        raise ValueError(f"{path}: {labels.shape[0]} vertices < {n}")
    labels = np.asarray(labels[:n], dtype=np.int64)   # fsaverage -> fsaverage5: first n vertices
    labels[labels < 0] = 0                             # vertices outside the colour table
    return labels, [x.decode() if isinstance(x, bytes) else str(x) for x in names]


def _combine(name: str, lh: tuple[np.ndarray, list[str]], rh: tuple[np.ndarray, list[str]],
             prefixes: tuple[str, str] = ("", ""), background: str | None = None) -> Atlas:
    """Concatenate hemispheres: LH ids unchanged, RH ids shifted past the LH ids; 0 shared."""
    (l_lab, l_names), (r_lab, r_names) = lh, rh
    off = len(l_names) - 1
    r = np.where(r_lab > 0, r_lab + off, 0)
    names = [background or l_names[0]]
    names += [prefixes[0] + s for s in l_names[1:]] + [prefixes[1] + s for s in r_names[1:]]
    return Atlas(name=name, labels=np.concatenate([l_lab, r]), names=tuple(names))


def _load_pair(key: str, cfg: dict[str, Any] | None) -> tuple[tuple, tuple]:
    n = int(_cfg(cfg)["n_vertices_per_hemi"])
    return _read_annot(atlas_file(key, "lh", cfg), n), _read_annot(atlas_file(key, "rh", cfg), n)


# ----------------------------------------------------------------------------- loaders

def load_schaefer400(cfg: dict[str, Any] | None = None) -> Atlas:
    """Schaefer-400 7Net on fsaverage5 (0 = medial wall, 1..200 LH, 201..400 RH)."""
    lh, rh = _load_pair("schaefer400_7", cfg)
    return _combine("schaefer400_7", lh, rh, background=MEDIAL_WALL)


def schaefer_network(name: str) -> str:
    """'7Networks_LH_Vis_1' -> 'Vis'."""
    parts = name.split("_")
    if len(parts) < 4 or not parts[0].endswith("Networks"):
        raise ValueError(f"not a Schaefer parcel name: {name!r}")
    return parts[2]


def schaefer_hemi(name: str) -> str:
    return name.split("_")[1]


def yeo7_from_schaefer(schaefer: Atlas, networks: list[str] | None = None) -> Atlas:
    """Yeo-7 labels derived from Schaefer names; ids follow ``networks`` order, 0 = medial wall."""
    networks = list(networks or load_config()["atlases"]["yeo7"]["networks"])
    lut = np.zeros(len(schaefer.names), dtype=np.int64)
    for pid in range(1, len(schaefer.names)):
        lut[pid] = networks.index(schaefer_network(schaefer.names[pid])) + 1
    return Atlas(name="yeo7", labels=lut[schaefer.labels], names=(MEDIAL_WALL, *networks))


def load_yeo7(cfg: dict[str, Any] | None = None) -> Atlas:
    c = _cfg(cfg)
    return yeo7_from_schaefer(load_schaefer400(cfg), c["yeo7"]["networks"])


def load_hcp_mmp1(cfg: dict[str, Any] | None = None) -> Atlas:
    """HCP-MMP1 (Glasser) cut from fsaverage to fsaverage5; 1..180 LH (L_*), 181..360 RH (R_*)."""
    lh, rh = _load_pair("hcp_mmp1", cfg)
    return _combine("hcp_mmp1", lh, rh)


def load_destrieux(cfg: dict[str, Any] | None = None) -> Atlas:
    """Destrieux a2009s on fsaverage5; names prefixed 'L '/'R '. Labelling only."""
    lh, rh = _load_pair("destrieux", cfg)
    return _combine("destrieux", lh, rh, prefixes=("L ", "R "))


def medial_wall_mask(schaefer: Atlas | None = None) -> np.ndarray:
    """Boolean (20484,) mask, True on the medial wall (Schaefer label 0)."""
    s = schaefer if schaefer is not None else load_schaefer400()
    return s.labels == s.background


@dataclass(frozen=True)
class AtlasSet:
    schaefer: Atlas
    yeo7: Atlas
    hcp: Atlas
    destrieux: Atlas

    @property
    def medial_wall(self) -> np.ndarray:
        return medial_wall_mask(self.schaefer)


def load_all(cfg: dict[str, Any] | None = None) -> AtlasSet:
    s = load_schaefer400(cfg)
    return AtlasSet(schaefer=s, yeo7=yeo7_from_schaefer(s, _cfg(cfg)["yeo7"]["networks"]),
                    hcp=load_hcp_mmp1(cfg), destrieux=load_destrieux(cfg))
