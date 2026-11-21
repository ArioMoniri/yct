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


# ---------------------------------------------------------------- D-078 (body: second category)
def d078_categories(cfg: dict) -> list[str]:
    return list(cfg["controls"]["refclips_d078"]["categories"])


def snapshot_name_d078(category: str, cfg: dict) -> str:
    return f"image_{category}{cfg['controls']['refclips_d078']['snapshot_file_suffix']}_snapshot.json"


def snapshot_name_eff(category: str, cfg: dict) -> str:
    """The snapshot a category is filtered from: D-078 for its categories, else D-074."""
    if category in d078_categories(cfg):
        return snapshot_name_d078(category, cfg)
    return snapshot_name_d074(category, cfg)


def image_log_rel(category: str, cfg: dict) -> str:
    d = cfg["controls"]["refclips_d078"]
    tag = category + (d["log_suffix"] if category in d078_categories(cfg) else "")
    return cfg["controls"]["refclips_auto"]["logs"]["image"].replace("<cat>", tag)


# ---------------------------------------------------------------- D-079 (v2 logs after BUG-036)
def check_d079_routing(cfg: dict) -> None:
    """v2 routing (v3 via effective_cfg, D-080): log_version v2|v3, category order = loc_categories, every
    log path ends in _<log_version>.jsonl and is distinct from the superseded logs. Raises CurationError
    (KeyError when the D-079 key is absent)."""
    d = cfg["controls"]["refclips_d079"]
    ver = d["log_version"]
    if ver not in ("v2", "v3"):
        raise CurationError(f"refclips_d079.log_version {ver!r} not in ('v2', 'v3')")
    if d["category_order"] != cfg["controls"]["refclips"]["loc_categories"]:
        raise CurationError("refclips_d079.category_order != refclips.loc_categories")
    old = {p for v in d["superseded_logs"].values() for p in v}
    for cat in d["category_order"]:
        p = d["logs"][cat]
        if p in old or not p.endswith(f"_{ver}.jsonl"):
            raise CurationError(f"{cat}: {p} is not a {ver} log path")


def effective_cfg(cfg: dict) -> dict:
    """D-080 (BUG-037): without controls.refclips_d080 the config itself (D-079 v2). With it, a deep copy
    whose refclips_d079 routes the v3 logs: log_version, logs and finality from D-080; superseded_logs =
    D-079's plus D-080 superseded_logs_add (the v2 run-1 evidence log); audit.c1_equivalence from D-080;
    flip_logs = the D-079 superseded logs the committed flip file lists. The input is never mutated."""
    import copy

    out = copy.deepcopy(cfg)
    d9 = out["controls"]["refclips_d079"]
    d9["flip_logs"] = copy.deepcopy(d9["superseded_logs"])
    d8 = out["controls"].get("refclips_d080")
    if not d8:
        return out
    d9.update(log_version=d8["log_version"], logs=copy.deepcopy(d8["logs"]), finality=d8["finality"])
    d9["superseded_logs"] = {c: list(v) + list(d8["superseded_logs_add"].get(c, []))
                             for c, v in d9["superseded_logs"].items()}
    d9["audit"]["c1_equivalence"] = bool(d8["audit_c1_equivalence"])
    return out


def image_log_v2(category: str, cfg: dict) -> str:
    """The only image-log path the D-079 runner reads or appends to."""
    check_d079_routing(cfg)
    return cfg["controls"]["refclips_d079"]["logs"][category]


def load_flips(path: Path, want_sha256: str, superseded: dict[str, list[str]]) -> dict[str, set[str]]:
    """The committed BUG-036 re-check list: per v1 log name, the sha256(title) keys whose C1 reading went
    inadmissible -> admissible under the fixed client. File sha must equal the frozen sha; every superseded
    log must be listed; any admissible -> inadmissible entry is refused (v1 never over-admitted)."""
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != want_sha256:
        raise CurationError(f"{Path(path).name}: sha256 differs from refclips_d079_artifacts.flip_sha256")
    doc = json.loads(data)
    names = {Path(p).name for v in superseded.values() for p in v}
    if set(doc.get("logs", {})) != names:
        raise CurationError(f"flip file logs {sorted(doc.get('logs', {}))} != superseded {sorted(names)}")
    out = {}
    for name, v in doc["logs"].items():
        if v.get("adm_to_inadm"):
            raise CurationError(f"{name}: adm_to_inadm is not empty: STOP to the owner")
        out[name] = set(v["inadm_to_adm"])
    return out


def header_for_d078(cfg: dict, category: str, utc_date: str, base_sha256: str) -> dict:
    d, d4 = cfg["controls"]["refclips_d078"], cfg["controls"]["refclips_d074"]
    return {
        "kind": "image",
        "decision": d["decision"],
        "amends": d["amends"],
        "category": category,
        "sources": [dict(x) for x in d["image_sources"][category]],
        "base_snapshot": snapshot_name_d074(category, cfg),
        "base_snapshot_sha256": base_sha256,
        "namespace": d4["namespace"],
        "api": d4["api"],
        "limit": d4["image_snapshot_limit"],
        "utc_date": utc_date,
    }


def build_d078_snapshot(header: dict, base: dict, fetch_members: Callable[[str, int, int], dict]) -> dict:
    """Base = the frozen D-074 snapshot's entries verbatim, first; then every added source, enumerated
    completely within the limit, unioned and deduplicated by title (first seen wins)."""
    nb = len(base["header"]["sources"])
    if base["header"]["sources"] != header["sources"][:nb] or nb >= len(header["sources"]):
        raise CurationError("D-078 header sources must extend the D-074 base sources")
    entries = list(base["entries"])
    seen = {e["title"] for e in entries}
    for src in header["sources"][nb:]:
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


def check_header_d078(snapshot: dict, cfg: dict, snapshot_dir: Path) -> None:
    h = snapshot["header"]
    base_sha = file_sha(Path(snapshot_dir) / snapshot_name_d074(h.get("category"), cfg))
    want = {**header_for_d078(cfg, h.get("category"), h["utc_date"], base_sha), "complete": True,
            "n_members": len(snapshot["entries"])}
    if h != want:
        raise CurationError(f"D-078 snapshot header {h} != config {want}")


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


class RevidMovedError(CurationError):
    """D-079: a file page's revision moved between the responses of one batch (paging or the C4 query)."""

    def __init__(self, title: str, msg: str):
        super().__init__(msg)
        self.title = title


def check_header(snapshot: dict, cfg: dict) -> None:
    h = snapshot["header"]
    want = header_for(h["kind"], cfg, h.get("category"), h["utc_date"])
    if h != want:
        raise CurationError(f"snapshot header {h} != config {want}")


def check_log(log: list[dict], snapshot: dict, cfg: dict, n_pass: int,
              extra_reasons: Iterable[str] = ()) -> list[dict]:
    """Log rows are the inspected candidates in ascending sha256(title) order, contiguous from the first,
    stopping at the n_pass-th pass. Returns the passing rows. `extra_reasons`: reasons added by a later
    amendment (D-079 identity_changed) without editing the frozen reject_reasons list."""
    reasons = set(cfg["controls"]["refclips"]["reject_reasons"]) | set(extra_reasons)
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


def query_pages(titles: list[str], params: dict, get=None, batch: int = 50) -> dict[str, dict]:
    """BUG-036: one prop=... query over `titles`, every continue key followed until batchcomplete, pages
    merged by requested title (templates concatenated in response order, imageinfo from the first response
    that has it). Fails closed: a response without continue or batchcomplete, a requested title absent from
    the pages, a page marked missing/invalid, or (when imageinfo is requested) no imageinfo raises
    CurationError; it is never read as an empty licence."""
    get = get or _get
    out: dict[str, dict] = {}
    want_ii = "imageinfo" in params.get("prop", "")
    for i in range(0, len(titles), batch):
        chunk = titles[i : i + batch]
        merged: dict[str, dict] = {t: {"templates": [], "imageinfo": None, "lastrevid": None} for t in chunk}
        cont: dict = {}
        for _ in range(10_000):
            d = get({"action": "query", "titles": "|".join(chunk), **params, **cont})
            q = d.get("query", {})
            back = {n["to"]: n["from"] for n in q.get("normalized", [])}
            for p in q.get("pages", []):
                t = back.get(p["title"], p["title"])
                if t not in merged:
                    raise CurationError(f"Commons returned an unrequested page {p['title']!r}")
                if p.get("missing") or p.get("invalid"):
                    raise CurationError(f"Commons page missing/invalid: {t!r}")
                merged[t]["seen"] = True
                merged[t]["templates"] += [x["title"] for x in p.get("templates", [])]
                if p.get("lastrevid") is not None:   # D-079: one revision across every continuation
                    if merged[t]["lastrevid"] not in (None, p["lastrevid"]):
                        raise RevidMovedError(t, f"lastrevid of {t!r} changed during paging")
                    merged[t]["lastrevid"] = p["lastrevid"]
                if p.get("imageinfo") and merged[t]["imageinfo"] is None:
                    merged[t]["imageinfo"] = p["imageinfo"][0]
            if "continue" in d:
                cont = {k: v for k, v in d["continue"].items()}
                continue
            if not d.get("batchcomplete"):
                raise CurationError(f"Commons response has neither continue nor batchcomplete "
                                    f"(batch {chunk[0]!r}..{chunk[-1]!r})")
            break
        else:
            raise CurationError(f"Commons continuation did not terminate (batch {chunk[0]!r}..{chunk[-1]!r})")
        for t, m in merged.items():
            if not m.get("seen"):
                raise CurationError(f"Commons response missing title {t!r}")
            if want_ii and m["imageinfo"] is None:
                raise CurationError(f"Commons returned no imageinfo for {t!r}")
            m["templates"] = list(dict.fromkeys(m["templates"]))
            m.pop("seen")
            out[t] = m
    return out


def page_meta(titles: list[str], get=None, batch: int = 50) -> dict[str, dict]:
    """Templates (for the licence) + imageinfo (url, size, mime, sha1, artist/credit) per title.
    BUG-036: paged to batchcomplete through query_pages; a file page with no templates at all after
    complete paging is refused (every Commons file page carries at least its licence template)."""
    pages = query_pages(
        titles,
        {
            "prop": "templates|imageinfo|info",
            "tlnamespace": "10",
            "tllimit": "max",
            "iiprop": "url|size|mime|sha1|extmetadata",
            "iiextmetadatafilter": "Artist|Credit|LicenseShortName|AttributionRequired",
        },
        get=get,
        batch=batch,
    )
    out: dict[str, dict] = {}
    for title, p in pages.items():
        if not p["templates"]:
            raise CurationError(f"no templates for {title!r} after complete paging")
        if p["lastrevid"] is None:
            raise CurationError(f"no lastrevid for {title!r} (prop=info)")
        ii = p["imageinfo"]
        em = ii.get("extmetadata", {})
        out[title] = {
            "templates": p["templates"],
            "url": ii.get("url"),
            "descriptionurl": ii.get("descriptionurl"),
            "width": ii.get("width"),
            "height": ii.get("height"),
            "mime": ii.get("mime"),
            "duration": ii.get("duration"),
            "commons_sha1": ii.get("sha1"),
            "read_revid": p["lastrevid"],
            "artist": em.get("Artist", {}).get("value", ""),
            "credit": em.get("Credit", {}).get("value", ""),
            "license_short": em.get("LicenseShortName", {}).get("value", ""),
        }
    return out



def _page_meta_c4_once(titles: list[str], get=None, batch: int = 50) -> dict[str, dict]:
    out = page_meta(titles, get=get, batch=batch)
    extra = query_pages(titles, {"prop": "imageinfo|info", "iiprop": "extmetadata",
                                 "iiextmetadatafilter": "ImageDescription|Categories|ObjectName"},
                        get=get, batch=batch)
    for t, p in extra.items():   # BUG-036: paged to batchcomplete, every title present (fail-closed)
        if p["lastrevid"] != out[t]["read_revid"]:   # D-079 re-check N3: C4 text from the judged revision
            raise RevidMovedError(t, f"C4 extmetadata revision {p['lastrevid']} of {t!r} != read_revid "
                                f"{out[t]['read_revid']}")
        em = p["imageinfo"].get("extmetadata", {})
        out[t].update(
            description=" ".join(em.get(k, {}).get("value", "") for k in ("ImageDescription", "ObjectName")),
            categories=em.get("Categories", {}).get("value", "").replace("|", " "))
    return out


def page_meta_c4(titles: list[str], get=None, batch: int = 50) -> dict[str, dict]:
    """page_meta + the description and category text read by the C4 metadata rule. D-079 re-check B1
    (stop_resolution.lastrevid_moved): a revision moving within the batch's responses (template paging, or
    the C4 query against the read revision) retries the whole batch once; a second move is a STOP to the
    council naming the title. Every other CurationError propagates at once (fail-closed)."""
    try:
        return _page_meta_c4_once(titles, get=get, batch=batch)
    except RevidMovedError:
        pass
    try:
        return _page_meta_c4_once(titles, get=get, batch=batch)
    except RevidMovedError as exc:
        raise CurationError(f"{exc} (after one retry): STOP to the council [{exc.title}]") from exc

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
