"""D-085 part 2 (speech + TALKFACE) pins recorded on the pod, before the part-2 freeze (not frozen here)."""
from __future__ import annotations

from yct.config import load_config
from yct.tribe_run import speech_corpus

CFG = load_config()
SP = CFG["controls"]["refclips_d085"]["speech"]
TF = CFG["controls"]["refclips_d085"]["talkface"]


def test_espeak_engine_is_pinned_to_the_pod_build():
    eng = SP["engine_pin"]
    assert eng["package"] == "espeak-ng 1.51+dfsg-12build1"
    assert eng["binary_sha256"] == "34191438b1e0f8f5aac5d4fdc5df574762b6fbb3c7a219a8c6f14feceb1bd076"
    assert eng["lib_sha256"] == "a18be542512749ea11dcbb5799f0de86a4bcacc75b3a625198160f67bfd37508"
    assert eng["data_tree_sha256"] == "f35962c893b17b538552fc4e0328af726c0b19ed1b388d8011323e265531a439"
    assert eng["native_sr"] == 22050 and eng["deterministic"] is True


def test_talkface_detector_readme_and_council_weights_pins():
    assert TF["face_detector_sha256"] == "619a31681264d3f7f7fc7a16a42cbbe8b23f31a256f75a366e5a1bcd59b33543"
    assert TF["readme_sha256"] == "8019ca16cf27529731bebed3c2f542046d6db1797cf38042cd1d27f4793ecd34"
    assert TF["weights_file"] == "Wav2Lip-SD-NOGAN.pt"   # council part 2: wav2lip.pth gone from README link
    assert TF["weights_sha256"] == "7ab9249147fd8d7884983567883222b7a86b6f94282354887825dfee7d608999"
    assert TF["mirror_s3"].endswith("private/") and TF["publish"] is False


def test_part2_keys_are_not_frozen_yet_and_synthesis_stays_refused():
    for k in CFG["controls"]["refclips_d085"]["freeze_plan"]["part2"]:
        assert not speech_corpus._frozen(CFG, k), k
    import pytest
    with pytest.raises(SystemExit, match="not frozen"):
        speech_corpus.require_frozen(CFG)
