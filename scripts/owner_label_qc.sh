#!/usr/bin/env bash
# YCT owner label QC (D-047, FIX-P1). OWNER ONLY. Runs on the owner's Mac (or AWS CloudShell) with the AWS
# CLI already logged in. No repo clone, no jq/brew; needs aws, curl, python3 (stdlib only) and tar.
# Paste the whole file into Terminal, or save it and run: bash owner_label_qc.sh
#
# It fetches the sealed archives + manifest from GitHub (gh api if installed, else the public API via curl),
# checks their sha256 files, reads the age key from SSM /yct/owner/age_key, decrypts into a private temp
# dir that is deleted on exit, then:
#   (a) label QC: compares the single-use re-derivation (data/sealed/rederive_wave1.tar.age, CSV
#       video_id,outcome,label_confidence) with the sealed labels on ALL in_primary rows and prints ONLY
#       n, Cohen's kappa (95% CI), agreement % and the disagreeing / missing video_ids (no labels);
#   (b) block codes: opaque exchangeability block codes for era_block x discovery route (D-040, D-047),
#       era blocks with < 6 videos merged within route; codes B1..Bk ordered by a secret random salt; written
#       to SSM /yct/owner/blocks as "video_id:code,..."; prints only the size of each code;
#   (c) spot-check: prints 10 random conf-A rows WITH labels for your manual check (ROADMAP P1 DoD).
#       Only you should see the screen for step (c). Nothing is written to disk outside the temp dir.
# Options (env): REF=<branch/sha> (default below), WRITE_BLOCKS=0 to skip the SSM write, SPOT_N=10.
REPO="ArioMoniri/yct"
REF="${REF:-claude/yc-videos-agent-system-dirk8p}"
WRITE_BLOCKS="${WRITE_BLOCKS:-1}"
SPOT_N="${SPOT_N:-10}"

set -euo pipefail
export AWS_DEFAULT_REGION=eu-central-1
umask 077
for c in aws curl python3 tar; do command -v "$c" >/dev/null || { echo "$c not found"; exit 1; }; done
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/enc" "$TMP/plain"
echo "Owner: $(aws sts get-caller-identity --query Arn --output text) | repo $REPO @ $REF"

api() {  # api <repo path> <dest> [raw]: GitHub contents API (raw bytes when $3 = raw)
  local accept="application/vnd.github+json"; [ "${3:-}" = raw ] && accept="application/vnd.github.raw"
  if command -v gh >/dev/null 2>&1 && gh api -H "Accept: $accept" "repos/$REPO/contents/$1?ref=$REF" > "$2" 2>/dev/null
  then return 0; fi
  curl -fsSL -H "Accept: $accept" "https://api.github.com/repos/$REPO/contents/$1?ref=$REF" -o "$2"
}

cat > "$TMP/qc.py" <<'PYQC'
"""Owner-side label QC (embedded in scripts/owner_label_qc.sh; tests extract and import this block).

Pure stdlib, Python >= 3.8. Subcommands: verify, extract, kappa, blocks, spot."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import random
import os
import secrets
import sys
import tarfile
from pathlib import Path

ROUTE_MERGE_MIN_VIDEOS = 6          # = config.yaml era_blocks.route_merge_min_videos (test-checked)
ERA_ORDER = ["E12", "E3", "UNKNOWN"]
ROUTE_COLUMNS = ("route", "discovery_route")
ROUTE_FALLBACKS = ("discovery", "discovery_method")
_OUT = {"accepted": "accepted", "accept": "accepted", "acc": "accepted", "a": "accepted", "1": "accepted",
        "true": "accepted", "yes": "accepted", "admitted": "accepted",
        "rejected": "rejected", "reject": "rejected", "rej": "rejected", "r": "rejected", "0": "rejected",
        "false": "rejected", "no": "rejected"}


def norm_outcome(v) -> str:
    s = str(v if v is not None else "").strip().lower()
    return _OUT.get(s, s)


def norm_conf(v) -> str:
    return str(v if v is not None else "").strip().upper()


# ---------------------------------------------------------------- statistics
def cohen_kappa(a, b):
    """(kappa, p_observed, p_expected) for two equal-length nominal ratings; kappa is nan if p_e == 1."""
    if len(a) != len(b) or not a:
        raise ValueError("need two non-empty rating lists of equal length")
    n = len(a)
    cats = sorted(set(a) | set(b))
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    k = float("nan") if pe >= 1 else (po - pe) / (1 - pe)
    return k, po, pe


def kappa_ci(po: float, pe: float, n: int, z: float = 1.96):
    """Large-sample 95% CI (Cohen 1960 SE), clipped to [-1, 1]; (nan, nan) if undefined."""
    if pe >= 1 or n == 0:
        return float("nan"), float("nan")
    k = (po - pe) / (1 - pe)
    se = math.sqrt(max(po * (1 - po), 0.0) / (n * (1 - pe) ** 2))
    return max(-1.0, k - z * se), min(1.0, k + z * se)


# ---------------------------------------------------------------- tables
def read_tables(root: Path):
    """[(path, rows)] for every .csv/.tsv/.json/.jsonl under root (rows = list of dicts)."""
    out = []
    for p in sorted(Path(root).rglob("*")):
        if not p.is_file():
            continue
        suf = p.suffix.lower()
        try:
            text = p.read_text(encoding="utf-8-sig")
        except (UnicodeDecodeError, OSError):
            continue
        rows = []
        if suf in (".csv", ".tsv"):
            rows = list(csv.DictReader(io.StringIO(text), delimiter="\t" if suf == ".tsv" else ","))
        elif suf == ".json":
            try:
                obj = json.loads(text)
            except ValueError:
                continue
            if isinstance(obj, dict):
                obj = obj.get("rows", obj.get("data", [obj]))
            rows = [o for o in obj if isinstance(o, dict)] if isinstance(obj, list) else []
        elif suf == ".jsonl":
            for line in text.splitlines():
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if isinstance(o, dict):
                    rows.append(o)
        rows = [{str(k).strip().lower(): ("" if v is None else str(v).strip()) for k, v in r.items()}
                for r in rows]
        if rows:
            out.append((p, rows))
    return out


def load_rows(root: Path, required=("video_id",)) -> dict:
    """Merge every table that has all `required` columns into {video_id: {column: value}}.

    The same video_id may appear in several tables (e.g. sealed parts); a column with two different
    non-empty values for one video_id is a conflict and raises (ids only, never values)."""
    merged: dict = {}
    conflicts = set()
    for _, rows in read_tables(root):
        if not all(c in rows[0] for c in required):
            continue
        for r in rows:
            vid = r.get("video_id", "")
            if not vid:
                continue
            cur = merged.setdefault(vid, {})
            for k, v in r.items():
                if v == "":
                    continue
                old = cur.get(k, "")
                same = (norm_outcome(old) == norm_outcome(v)) if k == "outcome" else old == v
                if old and not same:
                    conflicts.add(vid)
                else:
                    cur[k] = v
    if conflicts:
        raise SystemExit(f"CONFLICT: sealed tables disagree for {len(conflicts)} video_ids: {sorted(conflicts)}")
    return merged


def sealed_urls(root: Path) -> dict:
    """{id: url} from the sealed URL map (sealed_p1c_urls: columns file,id,url)."""
    out = {}
    for _, rows in read_tables(root):
        if {"file", "id", "url"} <= set(rows[0]):
            out.update({r["id"]: r["url"] for r in rows if r.get("id")})
    return out


def read_manifest(path: Path) -> list:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def primary_ids(manifest: list) -> list:
    return sorted(r["video_id"] for r in manifest if r.get("in_primary") == "True")


# ---------------------------------------------------------------- (a) label QC
def compare(sealed: dict, rederived: dict, ids: list) -> dict:
    """Agreement of re-derived vs sealed outcome on `ids`. Returns counts and ids only (no labels)."""
    missing_sealed = [i for i in ids if not sealed.get(i, {}).get("outcome")]
    if missing_sealed:
        raise SystemExit(f"sealed labels missing for {len(missing_sealed)} in_primary ids: {missing_sealed}")
    missing = [i for i in ids if not rederived.get(i, {}).get("outcome")]
    both = [i for i in ids if i not in missing]
    a = [norm_outcome(sealed[i]["outcome"]) for i in both]
    b = [norm_outcome(rederived[i]["outcome"]) for i in both]
    res = {"n_primary": len(ids), "n": len(both), "missing": missing,
           "disagree": [i for i, x, y in zip(both, a, b) if x != y]}
    if both:
        k, po, pe = cohen_kappa(a, b)
        res.update(kappa=k, ci=kappa_ci(po, pe, len(both)), agreement=po)
    else:
        res.update(kappa=float("nan"), ci=(float("nan"), float("nan")), agreement=float("nan"))
    if any("label_confidence" in rederived.get(i, {}) for i in both):
        res["not_conf_a"] = [i for i in both if norm_conf(rederived[i].get("label_confidence")) != "A"]
    return res


def format_compare(res: dict) -> str:
    lo, hi = res["ci"]
    lines = [f"in_primary rows: {res['n_primary']}; compared n = {res['n']}",
             f"Cohen's kappa (outcome) = {res['kappa']:.3f}  95% CI [{lo:.3f}, {hi:.3f}]",
             f"agreement = {100 * res['agreement']:.1f}%",
             f"disagreeing video_ids ({len(res['disagree'])}): {' '.join(res['disagree']) or '-'}",
             f"not re-derived ({len(res['missing'])}): {' '.join(res['missing']) or '-'}"]
    if "not_conf_a" in res:
        lines.append(f"re-derived confidence not A ({len(res['not_conf_a'])}): {' '.join(res['not_conf_a']) or '-'}")
    lines.append("PASS (kappa >= 0.9)" if res["kappa"] >= 0.9 else "BELOW 0.9 -> adjudicate the listed ids")
    return "\n".join(lines)


# ---------------------------------------------------------------- (b) block codes
def merge_within_route(counts: dict, min_videos: int = ROUTE_MERGE_MIN_VIDEOS) -> dict:
    """{era_block: n} for ONE route -> {era_block: merged key}. Mechanical, label-free: while some group
    has < min_videos and more than one group is left, the smallest group (earliest era on ties) merges
    into its later neighbour in ERA_ORDER (its earlier neighbour if it is last)."""
    order = sorted(counts, key=lambda e: (ERA_ORDER.index(e) if e in ERA_ORDER else len(ERA_ORDER), e))
    groups = [[[e], counts[e]] for e in order]
    while len(groups) > 1 and min(g[1] for g in groups) < min_videos:
        i = min(range(len(groups)), key=lambda j: (groups[j][1], j))
        j = i + 1 if i + 1 < len(groups) else i - 1
        lo, hi = sorted((i, j))
        groups[lo] = [groups[lo][0] + groups[hi][0], groups[lo][1] + groups[hi][1]]
        del groups[hi]
    return {e: "+".join(g[0]) for g in groups for e in g[0]}


def block_codes(rows, salt: str, min_videos: int = ROUTE_MERGE_MIN_VIDEOS) -> dict:
    """rows = [(video_id, era_block, route)] -> {video_id: "B<k>"}. Codes are opaque: blocks are numbered
    in the sorted order of sha256(salt | route | merged eras), so without the (secret) salt a code says
    nothing about the route."""
    by_route: dict = {}
    for _, era, route in rows:
        by_route.setdefault(route, {}).setdefault(era, 0)
        by_route[route][era] += 1
    merged = {r: merge_within_route(c, min_videos) for r, c in by_route.items()}
    key = {vid: f"{route}|{merged[route][era]}" for vid, era, route in rows}
    ordered = sorted(set(key.values()), key=lambda k: hashlib.sha256(f"{salt}|{k}".encode()).hexdigest())
    code = {k: f"B{i + 1}" for i, k in enumerate(ordered)}
    return {vid: code[k] for vid, k in key.items()}


def route_column(sealed: dict, ids: list) -> str:
    cols = set().union(*(sealed.get(i, {}).keys() for i in ids)) if ids else set()
    for c in ROUTE_COLUMNS:
        if c in cols:
            return c
    for c in ROUTE_FALLBACKS:
        if c in cols:
            return c
    raise SystemExit(f"no route column ({', '.join(ROUTE_COLUMNS + ROUTE_FALLBACKS)}) in the sealed tables")


def blocks_for(manifest: list, sealed: dict, salt: str | None = None):
    ids = primary_ids(manifest)
    era = {r["video_id"]: r.get("era_block") or "UNKNOWN" for r in manifest}
    col = route_column(sealed, ids)
    missing = [i for i in ids if not (sealed.get(i, {}).get(col) or "").strip()]
    default = os.environ.get("ROUTE_DEFAULT", "").strip()
    if missing and not default:
        raise SystemExit(f"route missing for {len(missing)} in_primary ids: {missing}")
    if missing:
        # D-049: opt-in only. Round-1 Curator left the route empty; its report states every round-1 row was
        # keyword_search except two directory_sweep rows (which carry the field).
        print(f"  route empty for {len(missing)} in_primary ids -> {default.upper()} (ROUTE_DEFAULT, D-049)")
    rows = [(i, era[i], ((sealed.get(i, {}).get(col) or "").strip() or default).upper()) for i in ids]
    codes = block_codes(rows, salt if salt is not None else secrets.token_hex(16))
    return codes, col


def ssm_value(codes: dict) -> str:
    return ",".join(f"{v}:{codes[v]}" for v in sorted(codes))


# ---------------------------------------------------------------- (c) spot-check
def spot_rows(manifest: list, sealed: dict, urls: dict, k: int = 10, rng=None) -> list:
    rng = rng or random.SystemRandom()
    murl = {r["video_id"]: r.get("url", "") for r in manifest}
    has_conf = any("label_confidence" in v for v in sealed.values())
    pool = sorted(v for v, r in sealed.items() if norm_conf(r.get("label_confidence")) == "A") if has_conf \
        else primary_ids(manifest)
    out = []
    for vid in rng.sample(pool, min(k, len(pool))):
        r = sealed.get(vid, {})
        url = r.get("url") or murl.get(vid, "")
        if url.startswith("sealed:"):
            url = urls.get(url[len("sealed:"):], url)
        out.append({"video_id": vid, "url": url, "outcome": norm_outcome(r.get("outcome", "")),
                    "claimed_batch": r.get("claimed_batch", ""),
                    "evidence": r.get("evidence_url") or r.get("ev") or "",
                    "quote": (r.get("quote") or "")[:200]})
    return out


# ---------------------------------------------------------------- utilities used by the shell part
def verify(enc_dir: Path) -> None:
    for s in sorted(Path(enc_dir).glob("*.sha256")):
        digest, name = s.read_text().split()[:2]
        f = Path(enc_dir) / Path(name).name
        if hashlib.sha256(f.read_bytes()).hexdigest() != digest:
            raise SystemExit(f"sha256 MISMATCH for {f.name}")
        print(f"  sha256 OK {f.name}")


def safe_extract(tar_path: Path, dest: Path) -> None:
    dest = Path(dest).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path) as tf:
        for m in tf.getmembers():
            target = (dest / m.name).resolve()
            if not (m.isfile() or m.isdir()) or (target != dest and dest not in target.parents):
                raise SystemExit(f"unsafe tar member in {Path(tar_path).name}: {m.name}")
        if hasattr(tarfile, "data_filter"):
            tf.extractall(dest, filter="data")
        else:
            tf.extractall(dest)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["verify", "extract", "kappa", "blocks", "spot"])
    ap.add_argument("--manifest")
    ap.add_argument("--sealed")
    ap.add_argument("--rederive")
    ap.add_argument("--enc")
    ap.add_argument("--tar")
    ap.add_argument("--dest")
    ap.add_argument("--out")
    ap.add_argument("--n", type=int, default=10)
    a = ap.parse_args(argv)
    if a.cmd == "verify":
        verify(Path(a.enc))
        return 0
    if a.cmd == "extract":
        safe_extract(Path(a.tar), Path(a.dest))
        return 0
    manifest = read_manifest(Path(a.manifest))
    sealed = load_rows(Path(a.sealed), required=("video_id", "outcome"))
    if a.cmd == "kappa":
        rederived = load_rows(Path(a.rederive), required=("video_id", "outcome"))
        print(format_compare(compare(sealed, rederived, primary_ids(manifest))))
    elif a.cmd == "blocks":
        codes, col = blocks_for(manifest, sealed)
        sizes: dict = {}
        for c in codes.values():
            sizes[c] = sizes.get(c, 0) + 1
        Path(a.out).write_text(ssm_value(codes))
        note = "" if col in ROUTE_COLUMNS else f" (route taken from sealed column '{col}')"
        print(f"{len(sizes)} blocks over {len(codes)} in_primary videos{note}: "
              + " ".join(f"{c}={sizes[c]}" for c in sorted(sizes, key=lambda x: int(x[1:]))))
    elif a.cmd == "spot":
        for r in spot_rows(manifest, sealed, sealed_urls(Path(a.sealed)), a.n):
            print(" | ".join(f"{k}={v}" for k, v in r.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
PYQC

echo "== 1. Fetch sealed archives + manifest =="
api data/sealed "$TMP/list.json"
NAMES=$(python3 -c 'import json,sys; print(" ".join(sorted(e["name"] for e in json.load(open(sys.argv[1])) if e["name"].endswith(".age"))))' "$TMP/list.json")
[ -n "$NAMES" ] || { echo "no sealed archives found at $REF"; exit 1; }
for n in $NAMES; do api "data/sealed/$n" "$TMP/enc/$n" raw; api "data/sealed/$n.sha256" "$TMP/enc/$n.sha256" raw; done
api data/manifest.csv "$TMP/manifest.csv" raw
python3 "$TMP/qc.py" verify --enc "$TMP/enc"

echo "== 2. Decrypt (age key from SSM; private temp dir, deleted on exit) =="
case "$(uname -s)-$(uname -m)" in
  Darwin-arm64) A=darwin-arm64 ;; Darwin-x86_64) A=darwin-amd64 ;;
  Linux-x86_64) A=linux-amd64 ;;  Linux-aarch64) A=linux-arm64 ;;
  *) echo "unsupported platform"; exit 1 ;;
esac
AGE=$(command -v age || true)
if [ -z "$AGE" ]; then
  curl -fsSL "https://github.com/FiloSottile/age/releases/download/v1.2.1/age-v1.2.1-$A.tar.gz" | tar xz -C "$TMP"
  AGE="$TMP/age/age"
fi
aws ssm get-parameter --name /yct/owner/age_key --with-decryption --query Parameter.Value --output text > "$TMP/age.key"
mkdir -p "$TMP/plain/labels" "$TMP/plain/rederive"
for n in $NAMES; do
  stem="${n%.tar.age}"
  "$AGE" -d -i "$TMP/age.key" -o "$TMP/$stem.tar" "$TMP/enc/$n"
  if [ "$stem" = rederive_wave1 ]; then d="$TMP/plain/rederive"; else d="$TMP/plain/labels/$stem"; fi
  python3 "$TMP/qc.py" extract --tar "$TMP/$stem.tar" --dest "$d"; rm -f "$TMP/$stem.tar"
  echo "  decrypted $n"
done
rm -f "$TMP/age.key"

echo "== 3a. Label QC: re-derivation vs sealed labels (all in_primary rows; ids only) =="
if [ -n "$(ls -A "$TMP/plain/rederive")" ]; then
  python3 "$TMP/qc.py" kappa --manifest "$TMP/manifest.csv" --sealed "$TMP/plain/labels" --rederive "$TMP/plain/rederive"
else
  echo "  data/sealed/rederive_wave1.tar.age not found at $REF - skipped"
fi

echo "== 3b. Opaque exchangeability block codes (era_block x route) =="
python3 "$TMP/qc.py" blocks --manifest "$TMP/manifest.csv" --sealed "$TMP/plain/labels" --out "$TMP/blocks.txt"
if [ "$WRITE_BLOCKS" = 1 ]; then
  TIER=Standard; [ "$(wc -c < "$TMP/blocks.txt")" -gt 4000 ] && TIER=Advanced
  python3 -c 'import json,sys; print(json.dumps({"Name":"/yct/owner/blocks","Type":"String","Tier":sys.argv[2],"Overwrite":True,"Value":open(sys.argv[1]).read()}))' \
    "$TMP/blocks.txt" "$TIER" > "$TMP/p.json"
  aws ssm put-parameter --cli-input-json "file://$TMP/p.json" >/dev/null; rm -f "$TMP/p.json"
  echo "  set /yct/owner/blocks ($TIER tier)"
else
  echo "  WRITE_BLOCKS=0: not written"
fi

echo "== 3c. Human spot-check: $SPOT_N random conf-A rows (labels shown - for your eyes only) =="
python3 "$TMP/qc.py" spot --manifest "$TMP/manifest.csv" --sealed "$TMP/plain/labels" --n "$SPOT_N"
echo "Done. Temp dir removed. Report back only: kappa line, disagreeing ids, and 'spot-check N/10 correct'."
