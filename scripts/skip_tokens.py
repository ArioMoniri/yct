"""Token-level skip/xfail site counter for check_test_weakening.py (BUG-010 recall fix, FIX-C3-ENG).

Counts skip/xfail *code* sites with Python's tokenize instead of a per-line regex, so that
  * string literals that only CONTAIN skip text (test fixtures, data) are ignored, but
  * f-string expressions are scanned as code (``f"{pytest.skip('x')}"``),
  * code after a string on the same line is scanned (``\"\"\"doc\"\"\"; pytest.skip("x")``, also when the
    triple-quoted string started on an earlier line: whole files are tokenized),
  * string arguments of exec/eval/compile are scanned as code (``exec("pytest.skip('x')")``),
  * ``pytest.importorskip``, ``pytest.skip.Exception``, ``pytest.mark.skip/skipif/xfail``,
    ``unittest.skip*``, ``self.skipTest``, ``SkipTest``, ``add_marker("skip")``,
    ``getattr(pytest, "skip")`` and ``from pytest import skip`` are all counted.
Unparseable snippets (diff fragments) are tried with an implicit open triple-quote before them; if no
interpretation tokenizes, the raw regex is used (recall first).
"""
from __future__ import annotations

import ast
import io
import re
import token
import tokenize

SKIP_NAMES = re.compile(
    r"(^|\.)(pytest\.(skip|xfail|importorskip)|pytest\.mark\.(skip|skipif|xfail)|unittest\.skip\w*|"
    r"(^|\.)mark\.(skip|skipif|xfail)|skipTest|SkipTest|skipUnless)$")
SKIP_WORD = re.compile(r"\b(skip|skipif|xfail|importorskip)\b")
RAW_RE = re.compile(r"pytest\.mark\.(skip|skipif|xfail)\b|pytest\.(skip|xfail|importorskip)\b|unittest\.skip"
                    r"|skipTest|SkipTest|add_marker\(|from\s+pytest\s+import\s+.*\b(skip|xfail|importorskip)\b")
EXEC_NAMES = {"exec", "eval", "compile"}
_FSTART = getattr(token, "FSTRING_START", None)
_TSTART = getattr(token, "TSTRING_START", None)


def _tokens(src: str) -> list[tokenize.TokenInfo]:
    return list(tokenize.generate_tokens(io.StringIO(src).readline))


def _string_value(tok: str):
    try:
        return ast.literal_eval(tok)
    except (ValueError, SyntaxError):
        return None


def _fstring_exprs(tok: str) -> list[str]:
    """Source of every {expression} inside an f-string token (Python < 3.12 tokenizes them as STRING)."""
    try:
        node = ast.parse(tok, mode="eval").body
    except SyntaxError:
        return [tok]  # undecidable: scan raw
    return [ast.unparse(v.value) for v in ast.walk(node) if isinstance(v, ast.FormattedValue)]


def _is_fstring(tok: str) -> bool:
    m = re.match(r"([A-Za-z]*)['\"]", tok)
    return bool(m and "f" in m.group(1).lower())


def count_tokens(toks: list[tokenize.TokenInfo], depth: int = 0) -> int:
    n = 0
    layout = (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
              tokenize.ENCODING, tokenize.ENDMARKER)
    code = [t for t in toks if t.type not in layout]
    i = 0
    while i < len(code):
        t = code[i]
        if t.type == tokenize.NAME:
            # dotted name chain a.b.c
            j, parts = i, [t.string]
            while j + 2 < len(code) and code[j + 1].string == "." and code[j + 2].type == tokenize.NAME:
                parts.append(code[j + 2].string)
                j += 2
            dotted = ".".join(parts)
            nxt = code[j + 1] if j + 1 < len(code) else None
            hit = [k for k in range(1, len(parts) + 1) if SKIP_NAMES.search(".".join(parts[:k]))]
            if hit and parts[hit[0]:hit[0] + 1] == ["Exception"]:
                # pytest.skip.Exception is a skip only when raised (not in pytest.raises / except)
                if i > 0 and code[i - 1].string == "raise":
                    n += 1
            elif hit:
                n += 1
            elif parts[-1] == "add_marker" and nxt is not None and nxt.string == "(":
                arg = code[j + 2] if j + 2 < len(code) else None
                if arg is not None and arg.type == tokenize.STRING and \
                        SKIP_WORD.search(str(_string_value(arg.string))):
                    n += 1
            elif dotted == "getattr" and nxt is not None and nxt.string == "(" and j + 4 < len(code):
                if code[j + 2].string == "pytest" and code[j + 4].type == tokenize.STRING and \
                        SKIP_WORD.search(str(_string_value(code[j + 4].string))):
                    n += 1
            elif dotted == "from" and j + 1 < len(code):
                # from pytest import skip, xfail  /  from unittest import skip
                k = i + 1
                mod = []
                while k < len(code) and code[k].string != "import":
                    mod.append(code[k].string)
                    k += 1
                if "".join(mod) in ("pytest", "unittest") and k < len(code):
                    k += 1
                    while k < len(code) and code[k].type in (tokenize.NAME, tokenize.OP) and \
                            code[k].string not in (";",) and code[k].start[0] == code[i].start[0]:
                        if code[k].type == tokenize.NAME and SKIP_WORD.search(code[k].string) or \
                                code[k].string in ("skipIf", "skipUnless"):
                            n += 1
                        k += 1
            elif dotted in EXEC_NAMES and nxt is not None and nxt.string == "(" and j + 2 < len(code):
                arg = code[j + 2]
                if arg.type == tokenize.STRING and depth < 5:
                    val = _string_value(arg.string)
                    if isinstance(val, str):  # f-string arguments are scanned by the STRING branch
                        n += count_source(val, depth + 1)
            i = j + 1
            continue
        if t.type == tokenize.STRING and _is_fstring(t.string) and depth < 5:
            n += sum(count_source(e, depth + 1) for e in _fstring_exprs(t.string))
        i += 1
    return n


def count_source(src: str, depth: int = 0) -> int:
    """Skip/xfail sites in a complete source text. Raises tokenize.TokenError/SyntaxError if untokenizable."""
    return count_tokens(_tokens(src), depth)


def count_snippet(src: str) -> int:
    """Best-effort count for a fragment (diff lines): as-is, or as the tail of an open triple-quoted
    string; max over the interpretations that tokenize; raw regex if none does (recall first)."""
    counts = []
    for prefix in ("", '"""', "'''"):
        try:
            counts.append(count_source(prefix + src + ("\n" if not src.endswith("\n") else "")))
        except (tokenize.TokenError, SyntaxError, IndentationError):
            continue
    if counts:
        return max(counts)
    return sum(len(RAW_RE.findall(line)) for line in src.splitlines())


def count_file(src: str | None) -> int:
    if not src:
        return 0
    try:
        return count_source(src)
    except (tokenize.TokenError, SyntaxError, IndentationError):
        return count_snippet(src)
