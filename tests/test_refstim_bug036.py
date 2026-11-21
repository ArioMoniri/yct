"""BUG-036: Commons metadata queries must page every continue key to batchcomplete, and fail closed."""
import pytest

from yct.curate import refstim as rs

LIC = [["Template:Information", "Template:Cc-by-4.0"], ["Template:Information", "Template:PD-self"],
       ["Template:Information", "Template:Cc-zero", "Template:Personality rights"]]
TITLES = [f"File:F{i}.jpg" for i in range(60)]
TPL = {t: (LIC[i % 3] + [f"Template:Filler{j}" for j in range(i % 9)]) for i, t in enumerate(TITLES)}


def fake_commons(cap=5, drop_batchcomplete=False, drop_title=None, no_imageinfo=None):
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
            p = {"title": t, "ns": 6}
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
        d = {"query": {"pages": pages}}
        if start + cap < len(flat):
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
