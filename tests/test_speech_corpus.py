"""D-085 draft (owner 2026-11-22, speech corpus approved): yct.tribe_run.speech_corpus.

Offline only: parsing a source page of the IEEE/Harvard layout, the frozen exclusion lexicon, sha256(text)
ordering, the hash-only public corpus file (no sentence text in the repo; owner 2026-11-22), resolving the
texts from the private raw page with fail-closed sha checks, the SPK 3-word lead rule, the -40 dBFS
span gate and the in-order replacement selector (with an injected fake synthesiser; nothing is synthesised
before speech_corpus_sha256 is frozen). The sentences below are synthetic test sentences written for this
file, not items of the IEEE/Harvard list."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from yct.config import load_config
from yct.tribe_run import speech_corpus as S  # noqa: N812

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config()
SPEC = CFG["controls"]["refclips_d085"]["speech"]
LEX = json.loads((ROOT / SPEC["lexicon_file"]).read_text())

HTML = """<h1>Test Sentences</h1>
<h2>List 1</h2><ol>
<li>The red kettle slid off the old shelf.</li>
<li>Paint the old jar a calm shade of green.</li>
<li>A plain cloth covers the wide table.</li>
</ol><h2>List 2</h2><ol>
<li>Soft rain fell on the dull gray stones.</li>
<li>Four cups of warm tea sat there.</li>
</ol>"""
RAW = HTML.encode("utf-8")
RAW_SHA = hashlib.sha256(RAW).hexdigest()


def _doc():
    return S.build_corpus(S.parse_harvard_html(HTML), LEX, SPEC, {"url": "x", "raw_sha256": RAW_SHA})


def _has_text(o):
    if isinstance(o, dict):
        return "text" in o or any(_has_text(v) for v in o.values())
    if isinstance(o, list):
        return any(_has_text(v) for v in o)
    return False


def test_parse_keeps_list_and_item_order():
    rows = S.parse_harvard_html(HTML)
    assert [(r["list"], r["item"]) for r in rows] == [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2)]
    assert rows[0]["text"] == "The red kettle slid off the old shelf."


def test_exclusion_reasons_cover_every_category():
    lex = {"motion": ["slid"], "face": ["faced"], "place": [], "body": [], "yc_startup_finance": []}
    assert "motion" in S.exclusion_reasons("The red kettle slid off the old shelf.", lex)
    assert "number" in S.exclusion_reasons("Four cups of warm tea faced us.", lex)
    assert "face" in S.exclusion_reasons("Four cups of warm tea faced us.", lex)
    assert S.exclusion_reasons("Paint the old jar a calm shade of green.", lex) == []
    assert "proper_noun" in S.exclusion_reasons("The boy met Tom by the gate.", lex)
    assert "proper_noun" not in S.exclusion_reasons("I saw the dog.", lex)
    assert "number" in S.exclusion_reasons("He sold 3 hats.", lex)


def test_lexicon_file_has_the_five_categories_lowercase_and_no_duplicates():
    assert set(LEX["categories"]) == {"yc_startup_finance", "face", "body", "place", "motion"}
    for cat, words in LEX["categories"].items():
        assert words == sorted(set(words)), cat
        assert all(w == w.lower() and " " not in w for w in words), cat
    for w in ("startup", "money", "face", "hand", "room", "run"):
        assert any(w in v for v in LEX["categories"].values())


def test_corpus_queue_is_ascending_sha256_of_text_and_excludes_with_reasons():
    rows = S.parse_harvard_html(HTML)
    doc = _doc()
    q = doc["queue"]
    assert [r["sha256"] for r in q] == sorted(r["sha256"] for r in q)
    want = {S.sha_text(r["text"]): (r["list"], r["item"]) for r in rows}
    for r in q + doc["excluded"]:
        assert want[r["sha256"]] == (r["list"], r["item"])
    assert S.sha_text("Paint the old jar a calm shade of green.") in {r["sha256"] for r in q}
    ex = {r["sha256"]: r["reasons"] for r in doc["excluded"]}
    assert ex[S.sha_text("Four cups of warm tea sat there.")] == ["number"]
    assert len(q) + len(ex) == len(rows)


def test_corpus_document_holds_no_sentence_text():
    doc = _doc()
    assert not _has_text(doc)
    assert "Paint" not in S.json.dumps(doc)


def test_resolve_texts_returns_the_queue_with_texts_after_sha_checks():
    doc = _doc()
    q = S.resolve_texts(doc, RAW)
    assert [r["sha256"] for r in q] == [r["sha256"] for r in doc["queue"]]
    for r in q:
        assert S.sha_text(r["text"]) == r["sha256"]


def test_resolve_texts_fails_closed_on_a_wrong_raw_page_or_item_sha():
    doc = _doc()
    with pytest.raises(S.CorpusStopError, match="raw"):
        S.resolve_texts(doc, RAW + b" ")
    bad = S.json.loads(S.json.dumps(doc))
    bad["queue"][0]["sha256"] = "0" * 64
    with pytest.raises(S.CorpusStopError, match="sha256"):
        S.resolve_texts(bad, RAW)
    gone = S.json.loads(S.json.dumps(doc))
    gone["queue"][0]["item"] = 99
    with pytest.raises(S.CorpusStopError, match="not in the source"):
        S.resolve_texts(gone, RAW)


def test_spk_word_count_is_three_for_every_slot():
    # owner 2026-11-22 (council D-085 (b)(ii)): 3-word leads only; the design_v2 2/3 balance is dropped
    n = CFG["controls"]["refclips"]["families"]["SPK"]
    counts = [S.spk_words(i, k, SPEC["spk_words"]) for i in range(n) for k in range(3)]
    assert counts == [3] * (3 * n)


def test_speech_span_trims_at_minus_40_dbfs():
    sr = 16000
    x = np.zeros(sr * 2)
    x[4000:12000] = 0.5
    x[3000] = 0.005          # below -40 dBFS (0.01): ignored
    s0, s1 = S.speech_span(x, sr, -40.0)
    assert (s0, s1) == (4000, 12000)
    with pytest.raises(ValueError, match="silent"):
        S.speech_span(np.zeros(100), sr, -40.0)


def _fake(durs):
    """synth(text) -> (wav, sr) whose -40 dBFS span lasts durs[text] s (default 1.2 s)."""
    sr = 16000

    def synth(text):
        d = durs.get(text, 1.2)
        x = np.zeros(int(sr * (d + 0.4)))
        x[int(0.2 * sr):int(0.2 * sr) + int(round(d * sr))] = 0.3
        return x, sr
    synth.verified = {"fake": "pin"}     # select needs a pin-verified synth (D-085 part 2, watchdog)
    return synth


def _queue(n):
    return [{"text": f"w{j}a w{j}b w{j}c w{j}d w{j}e.", "sha256": f"{j:064x}"} for j in range(n)]


def test_select_fills_families_in_order_with_in_order_replacement_and_logs_rejects():
    q = _queue(200)
    spec = dict(SPEC, counts={"SPK": 4, "BURST": 1, "TALKFACE": 1})
    durs = {"w0a w0b w0c": 0.6}                           # slot SPK u=0 (3 words) -> too short -> replaced
    for j in range(200):
        durs.setdefault(f"w{j}a w{j}b w{j}c w{j}d w{j}e. w{j + 1}a w{j + 1}b w{j + 1}c w{j + 1}d w{j + 1}e.",
                        5.0)
        durs.setdefault(f"w{j}a w{j}b w{j}c w{j}d w{j}e.", 3.0)
    sel = S.select(q, _fake(durs), spec)
    spk = sel["items"]["SPK"]
    assert [it["n_words"] for it in spk] == [3] * 4
    assert spk[0]["text"] == "w1a w1b w1c"                # w0 rejected, the next queue item took slot 0
    assert sel["rejects"][0]["text"] == "w0a w0b w0c" and sel["rejects"][0]["reason"] == "duration"
    used = [s for fam in sel["items"].values() for it in fam for s in it["source_sha256"]]
    assert len(used) == len(set(used))                    # each source sentence used at most once
    assert len(sel["items"]["BURST"][0]["source_sha256"]) == 2
    assert 4.0 <= sel["items"]["BURST"][0]["span_s"] <= 6.0


def test_select_stops_when_the_queue_is_exhausted():
    spec = dict(SPEC, counts={"SPK": 3, "BURST": 0, "TALKFACE": 0})
    with pytest.raises(S.CorpusStopError, match="exhausted"):
        S.select(_queue(5), _fake({f"w{j}a w{j}b w{j}c": 0.5 for j in range(5)}), spec)


def test_committed_corpus_file_matches_config_sha_and_is_deterministic():
    path = ROOT / SPEC["corpus_file"]
    doc = json.loads(path.read_text())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == \
        CFG["controls"]["refclips_artifacts"]["speech_corpus_sha256"]
    assert doc["source"]["n_sentences"] == 720
    assert len(doc["queue"]) + len(doc["excluded"]) == 720
    assert doc["synthesis"] == {k: SPEC[k] for k in ("engine", "voice", "rate_wpm", "pitch", "amplitude")}
    assert [r["sha256"] for r in doc["queue"]] == sorted(r["sha256"] for r in doc["queue"])
    assert not _has_text(doc)                                  # owner 2026-11-22: ids + sha256s only
    need = sum(SPEC["counts"].values()) + SPEC["counts"]["BURST"]   # BURST joins two sentences
    assert len(doc["queue"]) >= need


def test_synthesis_refused_until_the_corpus_sha_is_frozen():
    with pytest.raises(SystemExit, match="not frozen"):
        S.require_frozen(CFG)
