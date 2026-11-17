#!/usr/bin/env python3
"""Heuristic test-weakening detector for diffs under tests/ (v2.md §3: never weaken a test).

Per commit in --base..HEAD (or HEAD vs index with --staged), per test file, flags:
  * more assertion lines removed than added (assert, self.assert*, np.testing.assert*, pytest.raises);
  * more `def test_` functions removed than added (incl. deleting a test file);
  * newly added skip/xfail sites, counted with tokenize over the WHOLE file before and after the change
    (scripts/skip_tokens.py: string literals ignored, but f-string expressions, code after a string on the
    same line, exec/eval/compile string arguments, importorskip, skip.Exception, add_marker("skip"),
    getattr(pytest, "skip"), `from pytest import skip`, unittest skips are code) (BUG-010 recall fix);
  * loosened numeric thresholds: a line rewritten with only numbers changed where a tolerance
    (rel=, abs=, atol=, rtol=, tol=, eps=, delta=) grew, `places=` shrank, a bound after < / <= grew
    or a bound after > / >= shrank.
A commit whose message contains "[QA-approved test change]" is reported but not failed.
History allowlist (FIX-D032-1): config.yaml `guards.test_weakening_allowlist` entries
{commit: <full sha>, path: <test file>, kind: skip|assertion|testdef|threshold, ticket: BUG-/ENH-nnn}
excuse exactly that finding, reported as ALLOWLISTED; the ticket must exist in BUGS.md/ENHANCEMENTS.md.
There are no wildcards: every other finding, including new ones in the same commit/file, still fails.
An allowlist entry whose commit is in the checked range but matches no finding is itself a FAIL (dead
entries hide nothing today but could excuse a future rewrite); changes to the allowlist are policed by
check_guard_config.py.
Exit 1 on any unapproved finding.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import guardlib as g  # noqa: E402
import skip_tokens  # noqa: E402

APPROVAL = "[QA-approved test change]"
TEST_DIR = "tests/"
ASSERT_RE = re.compile(
    r"(^\s*assert\b|\bself\.assert\w*\(|\bnp\.testing\.assert|\bassert_\w+\(|pytest\.raises\()"
)
TESTDEF_RE = re.compile(r"^\s*(async\s+)?def\s+test_")

NUM_RE = re.compile(r"(?<![\w.])-?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?(?![\w.])")
LOOSER_IF_BIGGER_KW = {"rel", "abs", "atol", "rtol", "tol", "tolerance", "eps", "delta", "rel_tol", "abs_tol"}
LOOSER_IF_SMALLER_KW = {"places", "decimal"}


def skeleton(line: str) -> str:
    return NUM_RE.sub("N", line.strip())


def numbers_with_direction(line: str) -> list[tuple[float, int]]:
    """(value, direction): +1 = bigger is looser, -1 = smaller is looser, 0 = unknown."""
    out = []
    for m in NUM_RE.finditer(line):
        before = line[: m.start()].rstrip()
        kw = re.search(r"(\w+)\s*=$", before)
        op = re.search(r"(<=|>=|<|>)$", before)
        if kw and kw.group(1).lower() in LOOSER_IF_BIGGER_KW:
            d = 1
        elif kw and kw.group(1).lower() in LOOSER_IF_SMALLER_KW:
            d = -1
        elif op:
            d = 1 if op.group(1).startswith("<") else -1
        else:
            d = 0
        out.append((float(m.group()), d))
    return out


def parse_diff(diff: str) -> dict[str, tuple[list[str], list[str]]]:
    files: dict[str, tuple[list[str], list[str]]] = defaultdict(lambda: ([], []))
    cur = None
    for line in diff.splitlines():
        if line.startswith("diff --git"):
            cur = line.split(" b/", 1)[-1]
        elif line.startswith(("--- ", "+++ ")):
            continue
        elif cur and line.startswith("-"):
            files[cur][0].append(line[1:])
        elif cur and line.startswith("+"):
            files[cur][1].append(line[1:])
    return files


def analyse(diff: str, files: dict[str, tuple[str | None, str | None]] | None = None) -> list[str]:
    """Findings for a -U0 diff. `files` maps path -> (old content, new content); when given, skip sites are
    counted over the whole files (exact tokenization), else over the diff fragments (best effort)."""
    findings = []
    for path, (rem, add) in parse_diff(diff).items():
        n_ra = sum(bool(ASSERT_RE.search(x)) for x in rem)
        n_aa = sum(bool(ASSERT_RE.search(x)) for x in add)
        if n_ra > n_aa:
            findings.append(f"{path}: {n_ra - n_aa} assertion line(s) deleted")
        n_rt = sum(bool(TESTDEF_RE.search(x)) for x in rem)
        n_at = sum(bool(TESTDEF_RE.search(x)) for x in add)
        if n_rt > n_at:
            findings.append(f"{path}: {n_rt - n_at} test function(s) deleted")
        if files is not None and path in files and path.endswith(".py"):
            old, new = files[path]
            n_rs, n_as = skip_tokens.count_file(old), skip_tokens.count_file(new)
        else:
            n_rs = skip_tokens.count_snippet("\n".join(rem)) if rem else 0
            n_as = skip_tokens.count_snippet("\n".join(add)) if add else 0
        if n_as > n_rs:
            findings.append(f"{path}: {n_as - n_rs} skip/xfail marker(s) added")
        pool = defaultdict(list)
        for a in add:
            pool[skeleton(a)].append(a)
        for r in rem:
            sk = skeleton(r)
            if "N" not in sk or not pool.get(sk):
                continue
            a = pool[sk].pop(0)
            for (old, d), (new, _) in zip(numbers_with_direction(r), numbers_with_direction(a), strict=False):
                if d and (new - old) * d > 0:
                    findings.append(f"{path}: loosened threshold {old:g} -> {new:g}: {a.strip()}")
    return findings


KINDS = {"skip": "skip/xfail marker(s) added", "assertion": "assertion line(s) deleted",
         "testdef": "test function(s) deleted", "threshold": "loosened threshold"}


def allowlist() -> list[dict]:
    out = []
    for e in g.guard_config().get("test_weakening_allowlist") or []:
        if not isinstance(e, dict) or not re.fullmatch(r"[0-9a-f]{40}", str(e.get("commit", ""))):
            print(f"WARNING ignoring allowlist entry without a full commit SHA: {e}")
            continue
        if e.get("kind") not in KINDS:
            print(f"WARNING ignoring allowlist entry with unknown kind: {e}")
            continue
        if not g.ticket_exists(e.get("ticket", "")):
            print(f"WARNING ignoring allowlist entry: ticket {e.get('ticket')!r} not in BUGS/ENHANCEMENTS")
            continue
        out.append(e)
    return out


def allowlisted(commit: str, finding: str, entries: list[dict]) -> str | None:
    for e in entries:
        if e["commit"] == commit and finding.startswith(f"{e['path']}: ") and KINDS[e["kind"]] in finding:
            return e["ticket"]
    return None


def tests_diff(old: str, new: str | None) -> str:
    args = ["diff", "-U0", "--no-color", "--no-renames"]
    args += [old, "--cached"] if new is None else [old, new]
    return g.git(*args, "--", TEST_DIR)


def file_pairs(diff: str, old: str, new: str | None) -> dict[str, tuple[str | None, str | None]]:
    """(old, new) content of every file in the diff; new=None means the index (":")."""
    return {p: (None if old == g.EMPTY_TREE else g.show(old, p), g.show(new or ":", p))
            for p in parse_diff(diff)}


def main() -> int:
    ap = g.base_parser(__doc__, staged=True)
    ap.add_argument("msg_file", nargs="?", help="commit message file (commit-msg hook / --staged)")
    a = ap.parse_args()
    reports: list[tuple[str, list[str], bool]] = []
    allowed: list[tuple[str, str, str]] = []
    if a.staged:
        old = "HEAD" if g.ref_exists("HEAD") else g.EMPTY_TREE
        msg = Path(a.msg_file).read_text() if a.msg_file else ""
        d = tests_diff(old, None)
        reports.append(("staged", analyse(d, file_pairs(d, old, None)), APPROVAL in msg))
    else:
        entries = allowlist()
        used: set[int] = set()
        commits = g.commits_in_range(g.resolve_base(a.base))
        for c in commits:
            ps = g.parents(c)
            if len(ps) > 1:
                continue  # merge: branch commits are checked individually
            findings = []
            parent = ps[0] if ps else g.EMPTY_TREE
            d = tests_diff(parent, c)
            for f in analyse(d, file_pairs(d, parent, c)):
                t = allowlisted(c, f, entries)
                if t:
                    allowed.append((c[:12], f, t))
                    used.update(i for i, e in enumerate(entries) if e["commit"] == c
                                and f.startswith(f"{e['path']}: ") and KINDS[e["kind"]] in f)
                else:
                    findings.append(f)
            if findings:
                reports.append((c[:12], findings, APPROVAL in g.commit_message(c)))
        in_range = set(commits)
        dead = [f"unused allowlist entry {e['commit'][:12]} {e['path']} {e['kind']} ({e['ticket']}): "
                "matches no finding; remove it" for i, e in enumerate(entries)
                if i not in used and e["commit"] in in_range]
        if dead:
            reports.append(("allowlist", dead, False))
    for who, f, t in allowed:
        print(f"ALLOWLISTED ({t}) {who}: {f}")
    failed = False
    for who, findings, approved in reports:
        for f in findings:
            tag = "QA-approved" if approved else "FAIL"
            print(f"{tag} {who}: {f}")
        failed |= bool(findings) and not approved
    if not any(f for _, f, _ in reports):
        print("OK no test weakening detected")
    return 1 if failed else 0


if __name__ == "__main__":
    g.run(main)
