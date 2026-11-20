"""T-LIC / T-NAT (D-071 b/c): label-free curation of the P4b localiser photographs and naturalistic clips.

Snapshot first (full candidate list, committed by sha before any filter), then candidates are inspected in
ascending sha256(title) order and every inspected one is logged as pass/reject with a fixed reason code,
until exactly 20 pass per image category (NAT: 15). No YC/founder/analysis-company imagery; nothing here
reads labels, data/sealed/ or predictions. The NAT disjointness check compares URL / video-id hashes only.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable, Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REFSTIM = ROOT / "data" / "refstim"
LICENSES_MD = ROOT / "docs" / "stimuli" / "LICENSES.md"
API = "https://commons.wikimedia.org/w/api.php"
_LAST_REQUEST: dict[str, float] = {}


def _http_cfg() -> dict:
    from yct.config import load_config

    return load_config()["controls"]["curation_http"]


def user_agent() -> str:
    """Owner-approved User-Agent (config controls.curation_http.user_agent); never a default or curl UA."""
    return _http_cfg()["user_agent"]


def http_get(url: str, timeout: int = 300, opener=None, clock=None) -> bytes:
    """One polite GET: config UA, >= min_interval_s per host, Retry-After honoured, exponential backoff.
    A host still answering 429 after max_429_wait_s -> CurationError (STOP). No other client, UA or IP."""
    import time as _time
    import urllib.error
    import urllib.parse
    import urllib.request

    c = _http_cfg()
    opener = opener or urllib.request.urlopen
    clock = clock or _time
    host = urllib.parse.urlsplit(url).netloc
    req = urllib.request.Request(url, headers={"User-Agent": c["user_agent"]})
    first_429, attempt = None, 0
    while True:
        gap = c["min_interval_s"] - (clock.time() - _LAST_REQUEST.get(host, -1e18))
        if gap > 0:
            clock.sleep(gap)
        _LAST_REQUEST[host] = clock.time()
        try:
            with opener(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504):
                raise CurationError(f"HTTP {e.code} for {url}") from e
            now = clock.time()
            if e.code == 429:
                first_429 = now if first_429 is None else first_429
                if now - first_429 > c["max_429_wait_s"]:
                    raise CurationError(f"HTTP 429 from {host} for > {c['max_429_wait_s']} s: STOP") from e
            ra = e.headers.get("Retry-After") if e.headers else None
            wait = float(ra) if ra and str(ra).strip().isdigit() else c["backoff_base_s"] * 2 ** attempt
            attempt += 1
            clock.sleep(wait)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt >= 6:
                raise CurationError(f"network error for {url}: {e}") from e
            clock.sleep(c["backoff_base_s"] * 2 ** attempt)
            attempt += 1


LICENCE_FIELDS = ("file", "url", "pageid", "revid", "licence", "licence_template", "attribution", "sha256")
PERSONALITY = "Template:Personality rights"


def title_key(title: str) -> str:
    return hashlib.sha256(title.encode("utf-8")).hexdigest()


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=False) + "\n"


def write_json(path: Path, obj) -> str:
    text = canonical(obj)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------- snapshot
def header_for(kind: str, cfg: dict, category: str | None, utc_date: str) -> dict:
    r = cfg["controls"]["refclips"]
    if kind == "image":
        return {
            "kind": "image",
            "category": category,
            "queries": list(r["image_queries"][category]),
            "srnamespace": 6,
            "filetype": "bitmap",
            "limit": r["snapshot_limits"]["image"],
            "utc_date": utc_date,
        }
    return {
        "kind": "nat",
        "category": "nat",
        "queries": [r["nat_query"]],
        "srnamespace": 6,
        "filetype": "video",
        "limit": r["snapshot_limits"]["nat"],
        "utc_date": utc_date,
    }


def build_snapshot(header: dict, fetch: Callable[[str, int], list[dict]]) -> dict:
    """fetch(srsearch, limit) -> [{title, pageid, revid}] in API order; queries unioned (first seen)."""
    seen, entries = set(), []
    for q in header["queries"]:
        for e in fetch(f"{q} filetype:{header['filetype']}", header["limit"]):
            if e["title"] not in seen:
                seen.add(e["title"])
                entries.append(
                    {"title": e["title"], "pageid": int(e["pageid"]), "revid": int(e["revid"]), "query": q}
                )
    return {"header": header, "entries": entries}


# ---------------------------------------------------------------- D-074 category snapshot (images)
D074_FIELDS = ("title", "pageid", "revid", "mime", "mediatype", "sha1", "width", "height")


def snapshot_name_d074(category: str, cfg: dict) -> str:
    return f"image_{category}{cfg['controls']['refclips_d074']['snapshot_file_suffix']}_snapshot.json"


def header_for_d074(cfg: dict, category: str, utc_date: str) -> dict:
    d = cfg["controls"]["refclips_d074"]
    return {
        "kind": "image",
        "decision": d["decision"],
        "category": category,
        "sources": [dict(x) for x in d["image_sources"][category]],
        "namespace": d["namespace"],
        "api": d["api"],
        "limit": d["image_snapshot_limit"],
        "utc_date": utc_date,
    }


def build_category_snapshot(header: dict, fetch_members: Callable[[str, int, int], dict]) -> dict:
    """fetch_members(category, namespace, limit) -> {"complete": bool, "entries": [...D074_FIELDS]}.
    Every source must be complete and within the limit, else CurationError (nothing truncated). Sources are
    unioned, deduplicated by title (first source wins)."""
    seen, entries = set(), []
    for src in header["sources"]:
        r = fetch_members(src["category"], header["namespace"], header["limit"])
        if r.get("complete") is not True:
            raise CurationError(f"incomplete enumeration of Category:{src['category']}")
        if len(r["entries"]) > header["limit"]:
            raise CurationError(f"Category:{src['category']} has more than {header['limit']} files")
        for e in r["entries"]:
            missing = [f for f in D074_FIELDS if f not in e]
            if missing:
                raise CurationError(f"entry {e.get('title')!r} lacks {missing}")
            if e["title"] in seen:
                continue
            seen.add(e["title"])
            entries.append({**{f: e[f] for f in D074_FIELDS}, "source": src["category"]})
    return {"header": {**header, "complete": True, "n_members": len(entries)}, "entries": entries}


def check_header_d074(snapshot: dict, cfg: dict) -> None:
    h = snapshot["header"]
    want = {**header_for_d074(cfg, h.get("category"), h["utc_date"]), "complete": True,
            "n_members": len(snapshot["entries"])}
    if h != want:
        raise CurationError(f"D-074 snapshot header {h} != config {want}")


def pre_reason_d074(entry: dict, cfg: dict) -> str | None:
    """Reason fixed by the snapshot itself: a non-BITMAP entry is `not_photo` (= D-071 filetype:bitmap)."""
    if entry.get("mediatype") != cfg["controls"]["refclips_d074"]["bitmap_mediatype"]:
        return "not_photo"
    return None


def image_snapshot_sha_d074(snapshot_dir: Path, cfg: dict) -> str:
    """controls.refclips_artifacts.image_snapshot_sha256: sha256 of the concatenated bytes of the D-074
    face, body, place snapshot files in loc_categories order."""
    h = hashlib.sha256()
    for cat in cfg["controls"]["refclips"]["loc_categories"]:
        h.update((Path(snapshot_dir) / snapshot_name_d074(cat, cfg)).read_bytes())
    return h.hexdigest()


def ordered(snapshot: dict) -> list[dict]:
    return sorted(snapshot["entries"], key=lambda e: title_key(e["title"]))


# ---------------------------------------------------------------- licences
def licence_of(templates: Iterable[str], ext_license: str | None) -> tuple[str | None, str | None]:
    """(config licence label, template) from the file page's templates; None if not admissible.
    CC0 = Template:Cc-zero; PD-* = any Template:PD-...; CC-BY-x = Template:Cc-by-x (never -sa, nc, nd)."""
    t = list(templates)
    if PERSONALITY in t:
        return None, PERSONALITY
    for name in t:
        n = name.removeprefix("Template:")
        low = n.lower()
        if low == "cc-zero":
            return "CC0", name
        if n.startswith("PD-"):
            return "PD-*", name
        for v in ("2.0", "2.5", "3.0", "4.0"):
            if low == f"cc-by-{v}":
                return f"CC-BY-{v}", name
    return None, None


def attribution(artist_html: str, credit_html: str) -> str:
    """Plain-text 'Author (credit)' from Commons extmetadata HTML; never empty."""
    import html
    import re

    def plain(s: str) -> str:
        return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()

    a, c = plain(artist_html), plain(credit_html)
    return (f"{a} ({c})" if c and c != a else a) or c or "unknown author (see file page)"


def admissible(label: str | None, allowed: list[str]) -> bool:
    return label is not None and label in allowed


# ---------------------------------------------------------------- checks (T4 a-g)
class CurationError(RuntimeError):
    pass


def check_header(snapshot: dict, cfg: dict) -> None:
    h = snapshot["header"]
    want = header_for(h["kind"], cfg, h.get("category"), h["utc_date"])
    if h != want:
        raise CurationError(f"snapshot header {h} != config {want}")


def check_log(log: list[dict], snapshot: dict, cfg: dict, n_pass: int) -> list[dict]:
    """Log rows are the inspected candidates in ascending sha256(title) order, contiguous from the first,
    stopping at the n_pass-th pass. Returns the passing rows."""
    reasons = set(cfg["controls"]["refclips"]["reject_reasons"])
    order = ordered(snapshot)
    if len(log) > len(order):
        raise CurationError("log longer than snapshot")
    passes = []
    for i, row in enumerate(log):
        if row["title"] != order[i]["title"] or row["sha256_title"] != title_key(order[i]["title"]):
            raise CurationError(f"log row {i} out of sha256(title) order or gap: {row['title']!r}")
        if row["decision"] == "pass":
            if row.get("reason"):
                raise CurationError(f"pass row {i} carries a reason")
            passes.append(row)
        elif row["decision"] == "reject":
            if row.get("reason") not in reasons:
                raise CurationError(f"row {i} reason {row.get('reason')!r} not in reject_reasons")
        else:
            raise CurationError(f"row {i} decision {row['decision']!r}")
        if len(passes) == n_pass and i != len(log) - 1:
            raise CurationError("log continues after the last needed pass")
    if len(passes) != n_pass:
        raise CurationError(f"{len(passes)} passes, need exactly {n_pass}: the build does not start")
    return passes


def check_manifest(manifest: list[dict], cfg: dict, n_pass: int) -> None:
    allowed = cfg["controls"]["refclips"]["image_licences"]
    if len(manifest) != n_pass:
        raise CurationError(f"manifest has {len(manifest)} entries, need exactly {n_pass}")
    for m in manifest:
        if not admissible(m["licence"], allowed):
            raise CurationError(f"{m['file']}: licence {m['licence']!r} not admissible")
        if m["licence_template"] == PERSONALITY or m.get("personality_rights"):
            raise CurationError(f"{m['file']}: personality-rights template")
        if m["licence"] == "PD-*" and not m["licence_template"].removeprefix("Template:").startswith("PD-"):
            raise CurationError(f"{m['file']}: PD-* without a PD- template")
    if len({m["sha256"] for m in manifest}) != len(manifest):
        raise CurationError("duplicate sha256 in manifest")


def check_licenses_md(text: str, manifest: list[dict]) -> None:
    for m in manifest:
        line = next((ln for ln in text.splitlines() if f"| {m['file']} |" in ln), None)
        if line is None:
            raise CurationError(f"LICENSES.md has no row for {m['file']}")
        for f in LICENCE_FIELDS:
            if str(m[f]) not in line or not str(m[f]).strip():
                raise CurationError(f"LICENSES.md row for {m['file']} lacks {f}")


def licenses_md(sections: dict[str, list[dict]]) -> str:
    out = [
        "# Reference-stimulus licences (D-071 b/c)",
        "",
        "Per file: URL, page id, revision id, licence (config label), licence template, author/attribution,"
        " sha256 of the downloaded original. CC-BY files require the attribution shown.",
        "",
    ]
    for name, rows in sections.items():
        out += [
            f"## {name}",
            "",
            "| " + " | ".join(LICENCE_FIELDS) + " |",
            "|" + "---|" * len(LICENCE_FIELDS),
        ]
        for m in rows:
            out.append("| " + " | ".join(str(m[f]).replace("|", "/") for f in LICENCE_FIELDS) + " |")
        out.append("")
    return "\n".join(out)


def snapshot_precedes(repo: Path, snapshot_rel: str, later_rel: str) -> bool:
    """T4(a): the commit that first added `later_rel` has a strict ancestor containing `snapshot_rel` with the
    same blob as now."""

    def git(*a):
        return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True).stdout

    blob = git("rev-parse", f"HEAD:{snapshot_rel}").strip()
    adds = git("log", "--diff-filter=A", "--format=%H", "--", later_rel).split()
    if not adds:
        return False
    later = adds[-1]
    snap_adds = git("log", "--format=%H", f"{later}^", "--", snapshot_rel).split()
    for c in snap_adds:
        if git("rev-parse", f"{c}:{snapshot_rel}").strip() == blob:
            return (
                subprocess.run(
                    ["git", "-C", str(repo), "merge-base", "--is-ancestor", c, f"{later}^"]
                ).returncode
                == 0
            )
    return False


# ---------------------------------------------------------------- NAT disjointness (hashes only)
def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()


def nat_disjoint(nat_urls: Iterable[str], known_hashes: set[str]) -> bool:
    return not ({url_hash(u) for u in nat_urls} & known_hashes)


def known_url_hashes(paths: Iterable[Path]) -> set[str]:
    """sha256 of the `url` column of the given CSVs; no other column is read or kept."""
    import csv

    out: set[str] = set()
    for p in paths:
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("url"):
                    out.add(url_hash(row["url"]))
    return out


# ------------------------------------------------------------ Commons API (network; one request at a time)
def _get(params: dict, pause: float = 5.0) -> dict:
    import time
    import urllib.parse

    q = {"format": "json", "formatversion": "2", "maxlag": "5", **params}
    url = API + "?" + urllib.parse.urlencode(q)
    for attempt in range(6):
        d = json.loads(http_get(url, timeout=60))   # config UA, Retry-After, 429 STOP limit
        if "error" not in d and ("batchcomplete" in d or "query" in d or "continue" in d):
            time.sleep(pause)
            return d
        # maxlag or any API error: never read as "zero results"; back off and retry, never switch IP
        time.sleep(min(300, 15 * 2**attempt))
    raise CurationError(f"Commons API failed repeatedly for {params}")


def fetch_commons(srsearch: str, limit: int) -> list[dict]:
    """First `limit` search results in API (rank) order: title, pageid, revid (lastrevid)."""
    out: list[dict] = []
    offset = 0
    while len(out) < limit:
        d = _get(
            {
                "action": "query",
                "generator": "search",
                "gsrsearch": srsearch,
                "gsrnamespace": "6",
                "gsrlimit": str(min(500, limit - len(out))),
                "gsroffset": str(offset),
                "prop": "info",
            }
        )
        pages = sorted(d.get("query", {}).get("pages", []), key=lambda p: p["index"])
        out += [{"title": p["title"], "pageid": p["pageid"], "revid": p["lastrevid"]} for p in pages]
        if "continue" not in d or not pages:
            break
        offset = int(d["continue"]["gsroffset"])
    return out[:limit]


def page_meta(titles: list[str]) -> dict[str, dict]:
    """Templates (for the licence) + imageinfo (url, size, mime, sha1, artist/credit) per title."""
    out: dict[str, dict] = {}
    for i in range(0, len(titles), 50):
        batch = titles[i : i + 50]
        d = _get(
            {
                "action": "query",
                "titles": "|".join(batch),
                "prop": "templates|imageinfo",
                "tlnamespace": "10",
                "tllimit": "max",
                "iiprop": "url|size|mime|sha1|extmetadata",
                "iiextmetadatafilter": "Artist|Credit|LicenseShortName|AttributionRequired",
            }
        )
        for p in d.get("query", {}).get("pages", []):
            ii = (p.get("imageinfo") or [{}])[0]
            em = ii.get("extmetadata", {})
            out[p["title"]] = {
                "templates": [t["title"] for t in p.get("templates", [])],
                "url": ii.get("url"),
                "descriptionurl": ii.get("descriptionurl"),
                "width": ii.get("width"),
                "height": ii.get("height"),
                "mime": ii.get("mime"),
                "duration": ii.get("duration"),
                "commons_sha1": ii.get("sha1"),
                "artist": em.get("Artist", {}).get("value", ""),
                "credit": em.get("Credit", {}).get("value", ""),
                "license_short": em.get("LicenseShortName", {}).get("value", ""),
            }
    return out


def fetch_category(category: str, namespace: int, limit: int) -> dict:
    """D-074: every direct file member of Category:<category> (depth 0) with info + imageinfo. Follows every
    continue key (gcmcontinue and iicontinue) to batchcomplete; refuses beyond `limit`."""
    params = {
        "action": "query",
        "generator": "categorymembers",
        "gcmtitle": f"Category:{category}",
        "gcmtype": "file",
        "gcmnamespace": str(namespace),
        "gcmlimit": "500",
        "prop": "info|imageinfo",
        "iiprop": "mime|mediatype|sha1|size",
    }
    pages: dict[int, dict] = {}
    cont: dict = {}
    while True:
        d = _get({**params, **cont})
        for p in d.get("query", {}).get("pages", []):
            cur = pages.setdefault(p["pageid"], {"title": p["title"], "pageid": p["pageid"],
                                                 "revid": p.get("lastrevid")})
            ii = (p.get("imageinfo") or [None])[0]
            if ii:
                cur.update({"mime": ii.get("mime"), "mediatype": ii.get("mediatype"), "sha1": ii.get("sha1"),
                            "width": ii.get("width"), "height": ii.get("height")})
            if p.get("lastrevid"):
                cur["revid"] = p["lastrevid"]
        if len(pages) > limit:
            raise CurationError(f"Category:{category} has more than {limit} files")
        if "continue" in d:
            cont = d["continue"]
            continue
        if "batchcomplete" not in d:
            raise CurationError(f"Category:{category}: no batchcomplete and no continue")
        break
    return {"complete": True, "entries": sorted(pages.values(), key=lambda e: e["pageid"])}
