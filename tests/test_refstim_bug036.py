"""BUG-036: Commons metadata queries must page every continue key to batchcomplete, and fail closed."""
import pytest

from yct.curate import refstim as rs

LIC = [["Template:Information", "Template:Cc-by-4.0"], ["Template:Information", "Template:PD-self"],
       ["Template:Information", "Template:Cc-zero", "Template:Personality rights"]]
TITLES = [f"File:F{i}.jpg" for i in range(60)]
TPL = {t: (LIC[i % 3] + [f"Template:Filler{j}" for j in range(i % 9)]) for i, t in enumerate(TITLES)}


def fake_commons(cap=5, drop_batchcomplete=False, drop_title=None, no_imageinfo=None, missing=None,
                 invalid=None, extra_page=None, normalize=None, forever=False, revids=None):
    """A Commons stand-in with a per-request template cap shared across titles and tlcontinue paging."""
    calls = []

    def get(params, pause=0.0):
        calls.append(dict(params))
        titles = params["titles"].split("|")
        prop = params.get("prop", "")
        start = int(params.get("tlcontinue", "0"))
        flat = [(t, x) for t in titles for x in TPL[t]] if "templates" in prop else []
        chunk = flat[start:start + cap]
        pages = []
        for t in titles:
            if t == drop_title:
                continue
            p = {"title": (normalize or {}).get(t, t), "ns": 6}
            if t == missing:
                p["missing"] = True
            if t == invalid:
                p["invalid"] = True
            if "info" in prop.split("|"):
                p["lastrevid"] = (revids or {}).get((t, start), 100)
            got = [{"ns": 10, "title": x} for (tt, x) in chunk if tt == t]
            if got:
                p["templates"] = got
            if "imageinfo" in prop and t != no_imageinfo:
                p["imageinfo"] = [{"url": f"https://u/{t}", "width": 400, "height": 400, "mime": "image/jpeg",
                                   "sha1": "a" * 40, "descriptionurl": "d",
                                   "extmetadata": {"Artist": {"value": "A"},
                                                   "LicenseShortName": {"value": "x"},
                                                   "Categories": {"value": "c1|c2"},
                                                   "ImageDescription": {"value": "desc"}}}]
            pages.append(p)
        if extra_page:
            pages.append({"title": extra_page, "ns": 6})
        d = {"query": {"pages": pages}}
        if normalize:
            d["query"]["normalized"] = [{"from": k, "to": v} for k, v in normalize.items() if k in titles]
        if forever:
            d["continue"] = {"tlcontinue": "0", "continue": "||"}
        elif start + cap < len(flat):
            d["continue"] = {"tlcontinue": str(start + cap), "continue": "||"}
        elif not drop_batchcomplete:
            d["batchcomplete"] = True
        return d

    get.calls = calls
    return get


def test_templates_are_paged_to_batchcomplete():
    get = fake_commons(cap=5)
    meta = rs.page_meta(TITLES[:10], get=get)
    assert len(get.calls) > 1 and any("tlcontinue" in c for c in get.calls)
    for t in TITLES[:10]:
        assert meta[t]["templates"] == TPL[t]
        assert meta[t]["url"] == f"https://u/{t}"


def test_missing_batchcomplete_raises():
    with pytest.raises(rs.CurationError, match="batchcomplete"):
        rs.page_meta(TITLES[:3], get=fake_commons(cap=1000, drop_batchcomplete=True))


def test_missing_title_raises():
    with pytest.raises(rs.CurationError, match="missing"):
        rs.page_meta(TITLES[:3], get=fake_commons(cap=1000, drop_title=TITLES[1]))


def test_missing_imageinfo_raises():
    with pytest.raises(rs.CurationError, match="imageinfo"):
        rs.page_meta(TITLES[:3], get=fake_commons(cap=1000, no_imageinfo=TITLES[2]))


def test_page_without_templates_after_complete_paging_raises():
    TPL["File:Empty.jpg"] = []
    try:
        with pytest.raises(rs.CurationError, match="no templates"):
            rs.page_meta(["File:Empty.jpg"], get=fake_commons(cap=1000))
    finally:
        del TPL["File:Empty.jpg"]


@pytest.mark.parametrize("cap", [3, 500])
def test_decisions_independent_of_batch_boundaries(cap):
    decide = {}
    for bs in (1, 7, 50):
        meta = rs.page_meta(TITLES, get=fake_commons(cap=cap), batch=bs)
        decide[bs] = {t: rs.licence_of(meta[t]["templates"], meta[t]["license_short"]) for t in TITLES}
    assert decide[1] == decide[7] == decide[50]


def test_extmetadata_query_is_also_fail_closed():
    with pytest.raises(rs.CurationError, match="batchcomplete"):
        rs.query_pages(TITLES[:2], {"prop": "imageinfo", "iiprop": "extmetadata"},
                       get=fake_commons(drop_batchcomplete=True))


# ---------------------------------------------------------- QA (council D-078/D-079) fail-closed cases
def test_missing_page_raises():
    with pytest.raises(rs.CurationError, match="missing/invalid"):
        rs.page_meta(TITLES[:3], get=fake_commons(cap=1000, missing=TITLES[0]))


def test_invalid_page_raises():
    with pytest.raises(rs.CurationError, match="missing/invalid"):
        rs.page_meta(TITLES[:3], get=fake_commons(cap=1000, invalid=TITLES[2]))


def test_unrequested_page_raises():
    with pytest.raises(rs.CurationError, match="unrequested"):
        rs.page_meta(TITLES[:3], get=fake_commons(cap=1000, extra_page="File:Other.jpg"))


def test_normalized_titles_map_back_to_the_requested_title():
    TPL["File:a_b.jpg"] = LIC[0]
    try:
        get = fake_commons(cap=1000, normalize={"File:a_b.jpg": "File:A b.jpg"})
        meta = rs.page_meta(["File:a_b.jpg"], get=get)
        assert list(meta) == ["File:a_b.jpg"] and meta["File:a_b.jpg"]["templates"] == LIC[0]
    finally:
        del TPL["File:a_b.jpg"]


def test_continue_that_never_terminates_raises():
    with pytest.raises(rs.CurationError, match="did not terminate"):
        rs.query_pages(TITLES[:1], {"prop": "templates"}, get=fake_commons(cap=1000, forever=True))


def test_personality_rights_arriving_only_in_a_continuation_is_seen():
    t = TITLES[2]                                  # LIC[2]: Cc-zero then Personality rights (3rd template)
    get = fake_commons(cap=2)
    meta = rs.page_meta([t], get=get)
    assert len(get.calls) >= 2
    assert rs.licence_of(meta[t]["templates"], meta[t]["license_short"]) == (None, rs.PERSONALITY)


def test_read_revid_is_recorded():
    meta = rs.page_meta(TITLES[:2], get=fake_commons(cap=1000))
    assert all(meta[t]["read_revid"] == 100 for t in TITLES[:2])


def test_revid_changing_between_continuations_raises():
    t = TITLES[8]                                  # 8 filler templates: several continuation responses
    with pytest.raises(rs.CurationError, match="lastrevid"):
        rs.page_meta([t], get=fake_commons(cap=2, revids={(t, 0): 100, (t, 2): 101}))


def test_page_meta_c4_raises_on_truncated_extmetadata(monkeypatch):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "refstim_auto_run", Path(__file__).resolve().parents[1] / "scripts" / "refstim_auto_run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    good = fake_commons(cap=1000)
    trunc = fake_commons(cap=1000, drop_batchcomplete=True)

    def get(params, pause=0.0):
        return (good if "templates" in params.get("prop", "") else trunc)(params, pause)

    monkeypatch.setattr(rs, "_get", get)
    with pytest.raises(rs.CurationError, match="batchcomplete"):
        mod.page_meta_c4(TITLES[:2])
