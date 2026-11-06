"""Bounded, offline lexical intake for JavaScript and TypeScript projects.

Produces the same artifact set and schemas as the Python ``project-intake`` so
``design``, ``review``, ``document``, ``doc-gate``, ``source-impact`` and
``structure-diff`` work unchanged. No source is imported, executed, bundled or
sent anywhere: files are read as bytes, decoded and passed through a small
hand-written lexer. Nothing here is a JavaScript parser and nothing is
semantic: every import edge is a *syntax observation* of a string literal.
User-supplied business goals and requirements are NOT inferred from code.

Lexer scope (see ``docs/javascript-project-intake.md`` for the exact limits):

* comments, single/double-quoted strings, template literals (``${}`` nesting,
  iterative so hostile nesting cannot raise ``RecursionError``) and regex
  literals are skipped so text inside them is never read as code;
* regex-vs-division uses the standard "previous significant token" heuristic;
  slashes it cannot decide (after ``)`` or ``}``) are counted, not hidden;
* recognised: static ``import``/``export ... from`` (top level), ``require('x')``
  and ``import('x')`` with one string literal anywhere, and top-level
  ``function``/``class``/``interface``/``type``/``enum``/``const``/``let``/``var``
  declarations at bracket depth 0.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
import hashlib
import posixpath
from pathlib import PurePosixPath
import re
from typing import NamedTuple

from .fixtures import FixtureDesign
from .models import Component, Relationship
from .proposer import ComponentProposal
from .source_evidence import SourceClaim, SourceEvidence, read_safe_source_bytes, scan_sources

# .mts/.cts are listed for forward compatibility only: the shared inventory
# allowlist (source_evidence.SOURCE_SUFFIXES) does not contain them today, so
# they are neither inventoried nor analysed.
JS_SUFFIXES = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")
_TS_COUNTERPARTS = {
    ".js": (".ts", ".tsx"), ".jsx": (".tsx",), ".mjs": (".mts",), ".cjs": (".cts",),
}
MAX_SYMBOLS = 30
MAX_TEMPLATE_NESTING = 200
MAX_SPECIFIER_CHARS = 200
MAX_IMPORT_SCAN_TOKENS = 5000

_WS = re.compile(r"[ \t\r\n\f\v\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+")
_IDENT = re.compile(r"[^\W\d][\w$]*|\$[\w$]*")
_NUMBER = re.compile(r"\d[\w.]*")
_NEWLINES = "\n\r\u2028\u2029"
_FAST_PUNCT = frozenset("{}()[];,:")
_REGEX_KEYWORDS = frozenset({
    "return", "typeof", "instanceof", "in", "of", "new", "delete", "void",
    "throw", "case", "do", "else", "yield", "await",
})
_MODIFIERS = frozenset({"export", "default", "declare", "abstract", "async", "const"})
_DECLARATION_HEADS = frozenset({"import", "export", "const", "let", "var", "function", "class"})


class Token(NamedTuple):
    kind: str            # ident | string | template | regex | number | punct
    value: str | None    # string: decoded-free content (None if it has escapes / is broken)
    line: int
    nl_before: bool
    depth: int           # bracket depth surrounding the token


@dataclass(frozen=True)
class JsReference:
    kind: str                 # static | require | dynamic
    specifier: str | None     # None: non-literal argument
    line: int
    type_only: bool = False


@dataclass
class JsScan:
    references: list[JsReference] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    variables: list[str] = field(default_factory=list)
    ambiguous_slashes: int = 0
    anomalies: int = 0


def _skip_quoted(src: str, start: int) -> tuple[int, bool, bool, int]:
    """Scan a ' or " string. Returns (end, closed, has_escape, anomalies).

    A raw line break ends the literal (recovery: JSX text such as ``don't`` is
    not a string); the break itself is not consumed.
    """
    quote = src[start]
    n = len(src)
    j = start + 1
    escaped = False
    while True:
        if j >= n:
            return n, False, escaped, 1
        ch = src[j]
        if ch == quote:
            return j + 1, True, escaped, 0
        if ch == "\\":
            escaped = True
            j += 2
            continue
        if ch in "\n\r":
            return j, False, escaped, 1
        j += 1


def _skip_template(src: str, start: int) -> tuple[int, int]:
    """Skip a template literal incl. nested ``${}``/templates. Returns (end, anomalies).

    Iterative (explicit stack). Inside ``${ }`` only strings, nested templates,
    comments and braces are understood; a regex literal containing a quote,
    backtick or brace inside ``${ }`` can desynchronise this scan.
    """
    n = len(src)
    anomalies = 0
    modes = ["T"]
    braces: list[int] = []
    j = start + 1
    while modes:
        if len(modes) > MAX_TEMPLATE_NESTING:
            return n, anomalies + 1
        if j >= n:
            return n, anomalies + 1
        ch = src[j]
        if modes[-1] == "T":
            if ch == "\\":
                j += 2
            elif ch == "`":
                modes.pop()
                j += 1
            elif ch == "$" and src.startswith("{", j + 1):
                modes.append("E")
                braces.append(1)
                j += 2
            else:
                j += 1
            continue
        if ch == "{":
            braces[-1] += 1
            j += 1
        elif ch == "}":
            braces[-1] -= 1
            j += 1
            if braces[-1] == 0:
                braces.pop()
                modes.pop()
        elif ch == "`":
            modes.append("T")
            j += 1
        elif ch in "'\"":
            j, _closed, _esc, extra = _skip_quoted(src, j)
            anomalies += extra
        elif ch == "/" and src.startswith("/", j + 1):
            end = src.find("\n", j)
            j = n if end < 0 else end
        elif ch == "/" and src.startswith("*", j + 1):
            end = src.find("*/", j + 2)
            if end < 0:
                return n, anomalies + 1
            j = end + 2
        else:
            j += 1
    return j, anomalies


def _scan_regex(src: str, start: int) -> int | None:
    """End offset of a regex literal starting at ``/``, or None if it is not one."""
    n = len(src)
    j = start + 1
    in_class = False
    while j < n:
        ch = src[j]
        if ch == "\\":
            if j + 1 >= n or src[j + 1] in _NEWLINES:
                return None
            j += 2
            continue
        if ch in _NEWLINES:
            return None
        if in_class:
            if ch == "]":
                in_class = False
        elif ch == "[":
            in_class = True
        elif ch == "/":
            j += 1
            flags = _IDENT.match(src, j)
            return flags.end() if flags else j
        j += 1
    return None


def _regex_allowed(prev: Token | None, before: Token | None = None) -> bool:
    if prev is None:
        return True
    if prev.kind == "ident":
        # `obj.in / 2`: a keyword used as a property name is a value, not a keyword.
        if before is not None and before.kind == "punct" and before.value in {".", "?."}:
            return False
        return prev.value in _REGEX_KEYWORDS
    if prev.kind == "punct":
        # '<' is excluded so JSX closing tags (</div>) are not read as regexes.
        return prev.value not in {")", "]", "}", "++", "--", "<"}
    return False


def _lex(src: str) -> tuple[list[Token], int, int]:
    n = len(src)
    newlines: list[int] = []
    pos = src.find("\n")
    while pos >= 0:
        newlines.append(pos)
        pos = src.find("\n", pos + 1)

    def line_of(offset: int) -> int:
        return bisect.bisect_left(newlines, offset) + 1

    tokens: list[Token] = []
    ambiguous = 0
    anomalies = 0
    depth = 0
    prev_end_line = 1
    i = 0
    if src.startswith("\ufeff"):
        i = 1
    if src.startswith("#!", i):
        end = src.find("\n", i)
        i = n if end < 0 else end

    def push(kind: str, value: str | None, start: int, end: int, tok_depth: int) -> None:
        nonlocal prev_end_line
        line = bisect.bisect_left(newlines, start) + 1
        tokens.append(Token(kind, value, line, line > prev_end_line, tok_depth))
        prev_end_line = line if src.find("\n", start, end) < 0 else line_of(end)

    while i < n:
        ch = src[i]
        if ch in " \t\n":
            i += 1
            continue
        ws = _WS.match(src, i)
        if ws:
            i = ws.end()
            continue
        if ch == "/":
            following = src[i + 1:i + 2]
            if following == "/":
                end = src.find("\n", i)
                i = n if end < 0 else end
                continue
            if following == "*":
                end = src.find("*/", i + 2)
                if end < 0:
                    anomalies += 1
                    i = n
                else:
                    i = end + 2
                continue
            prev = tokens[-1] if tokens else None
            if _regex_allowed(prev, tokens[-2] if len(tokens) > 1 else None):
                end = _scan_regex(src, i)
                if end is not None:
                    push("regex", None, i, end, depth)
                    i = end
                    continue
                anomalies += 1
            elif prev is not None and prev.kind == "punct" and prev.value in {")", "}"}:
                ambiguous += 1
            push("punct", "/", i, i + 1, depth)
            i += 1
            continue
        if ch in "'\"":
            end, closed, escaped, extra = _skip_quoted(src, i)
            anomalies += extra
            value = src[i + 1:end - 1] if closed and not escaped else None
            push("string", value, i, end, depth)
            i = end
            continue
        if ch == "`":
            end, extra = _skip_template(src, i)
            anomalies += extra
            push("template", None, i, end, depth)
            i = end
            continue
        if ch in _FAST_PUNCT:
            punct = ch
        else:
            ident = _IDENT.match(src, i)
            if ident:
                push("ident", ident.group(), i, ident.end(), depth)
                i = ident.end()
                continue
            number = _NUMBER.match(src, i)
            if number:
                push("number", number.group(), i, number.end(), depth)
                i = number.end()
                continue
            if src.startswith("...", i):
                punct = "..."
            elif src.startswith("=>", i):
                punct = "=>"
            elif src.startswith("?.", i) and not src[i + 2:i + 3].isdigit():
                punct = "?."
            elif src.startswith("++", i) or src.startswith("--", i):
                punct = src[i:i + 2]
            else:
                punct = ch
        if punct in {"{", "(", "["}:
            push("punct", punct, i, i + 1, depth)
            depth += 1
        elif punct in {"}", ")", "]"}:
            if depth == 0:
                anomalies += 1
            else:
                depth -= 1
            push("punct", punct, i, i + 1, depth)
        else:
            push("punct", punct, i, i + len(punct), depth)
        i += len(punct)
    return tokens, ambiguous, anomalies


def _is(tok: Token | None, kind: str, value: str | None = None) -> bool:
    return tok is not None and tok.kind == kind and (value is None or tok.value == value)


def _statement_start(tokens: list[Token], k: int) -> bool:
    if k == 0:
        return True
    prev = tokens[k - 1]
    if prev.kind == "punct":
        if prev.value in {";", "}"}:
            return True
        if prev.value in {")", "]"}:
            return tokens[k].nl_before
        return False
    return tokens[k].nl_before


def _declaration_start(tokens: list[Token], k: int) -> bool:
    """Statement start for ``k`` after skipping modifier keywords (export default async ...)."""
    j = k
    while (j > 0 and tokens[j - 1].kind == "ident" and tokens[j - 1].value in _MODIFIERS
           and tokens[j - 1].depth == 0):
        j -= 1
    return _statement_start(tokens, j)


def _add(names: list[str], name: str | None) -> None:
    if name and name not in names:
        names.append(name)


def _is_method_definition(tokens: list[Token], open_index: int) -> bool:
    """True when the ``(`` at ``open_index`` closes into ``) {`` (a method named require/import)."""
    depth = tokens[open_index].depth
    for j in range(open_index + 1, min(len(tokens), open_index + 200)):
        tok = tokens[j]
        if tok.kind == "punct" and tok.value == ")" and tok.depth == depth:
            return j + 1 < len(tokens) and _is(tokens[j + 1], "punct", "{")
    return False


def scan_js_source(text: str) -> JsScan:
    """Lex ``text`` and return import references and top-level declaration names."""
    tokens, ambiguous, anomalies = _lex(text)
    scan = JsScan(ambiguous_slashes=ambiguous, anomalies=anomalies)
    found: list[tuple[int, JsReference]] = []
    count = len(tokens)

    def at(index: int) -> Token | None:
        return tokens[index] if 0 <= index < count else None

    for k, tok in enumerate(tokens):
        if tok.kind != "ident":
            continue
        word = tok.value
        prev = at(k - 1)
        member = _is(prev, "punct", ".") or _is(prev, "punct", "?.")
        nxt = at(k + 1)
        # require('x') / import('x') anywhere (never member access or a declaration).
        if (word in {"require", "import"} and _is(nxt, "punct", "(") and not member
                and not _is(prev, "ident", "function") and not _is_method_definition(tokens, k + 1)):
            arg, after = at(k + 2), at(k + 3)
            closers = {")"} if word == "require" else {")", ","}
            literal = (arg is not None and arg.kind == "string" and arg.value is not None
                       and after is not None and after.kind == "punct" and after.value in closers)
            found.append((k, JsReference(
                "require" if word == "require" else "dynamic",
                arg.value if literal else None, tok.line)))
            continue
        if tok.depth != 0 or member:
            continue
        if word == "import" and _statement_start(tokens, k):
            ref = _static_import(tokens, k)
            if ref:
                found.append((k, ref))
        elif word == "export" and _statement_start(tokens, k):
            ref = _static_export(tokens, k)
            if ref:
                found.append((k, ref))
        elif word == "function" and _declaration_start(tokens, k):
            j = k + 1
            if _is(at(j), "punct", "*"):
                j += 1
            name = at(j)
            if name is not None and name.kind == "ident":
                _add(scan.functions, name.value)
        elif word == "class" and _declaration_start(tokens, k):
            name = at(k + 1)
            if name is not None and name.kind == "ident" and name.value not in {"extends", "implements"}:
                _add(scan.classes, name.value)
        elif word in {"interface", "enum"} and _declaration_start(tokens, k):
            name = at(k + 1)
            if name is not None and name.kind == "ident" and not name.nl_before:
                _add(scan.classes, name.value)
        elif word == "type" and _declaration_start(tokens, k):
            name, after = at(k + 1), at(k + 2)
            if (name is not None and name.kind == "ident" and not name.nl_before
                    and after is not None and after.kind == "punct" and after.value in {"=", "<"}):
                _add(scan.classes, name.value)
        elif word in {"const", "let", "var"} and _declaration_start(tokens, k):
            name = at(k + 1)
            if name is not None and name.kind == "ident" and name.value != "enum":
                _add(scan.variables, name.value)
    found.sort(key=lambda pair: pair[0])
    scan.references = [ref for _index, ref in found]
    return scan


def _static_import(tokens: list[Token], k: int) -> JsReference | None:
    first = tokens[k + 1] if k + 1 < len(tokens) else None
    if first is None:
        return None
    line = tokens[k].line
    if first.kind == "string":
        return JsReference("static", first.value, line)
    j = k + 1
    type_only = False
    if _is(first, "ident", "type"):
        second = tokens[k + 2] if k + 2 < len(tokens) else None
        if second is not None and not _is(second, "punct", ",") and not (
                _is(second, "ident", "from") and k + 3 < len(tokens)
                and tokens[k + 3].kind == "string"):
            type_only = True
            j = k + 2
    return _scan_from_clause(tokens, j, line, type_only, stop_on_equals=True)


def _scan_from_clause(
    tokens: list[Token], j: int, line: int, type_only: bool, *, stop_on_equals: bool,
) -> JsReference | None:
    local = 0
    steps = 0
    while j < len(tokens) and steps < MAX_IMPORT_SCAN_TOKENS:
        tok = tokens[j]
        if tok.kind == "punct":
            if tok.value == "{":
                local += 1
            elif tok.value == "}":
                local -= 1
            elif tok.value == ";" or (stop_on_equals and tok.value == "=" and local == 0):
                return None
        elif tok.kind == "ident":
            if local == 0 and tok.value == "from":
                target = tokens[j + 1] if j + 1 < len(tokens) else None
                if target is not None and target.kind == "string":
                    return JsReference("static", target.value, line, type_only)
                return None
            if local == 0 and tok.nl_before and tok.value in _DECLARATION_HEADS:
                return None
        j += 1
        steps += 1
    return None


def _static_export(tokens: list[Token], k: int) -> JsReference | None:
    count = len(tokens)
    line = tokens[k].line
    j = k + 1
    type_only = False
    if (j + 1 < count and _is(tokens[j], "ident", "type")
            and tokens[j + 1].kind == "punct" and tokens[j + 1].value in {"{", "*"}):
        type_only = True
        j += 1
    if j >= count or tokens[j].kind != "punct" or tokens[j].value not in {"*", "{"}:
        return None
    if tokens[j].value == "{":
        local = 0
        while j < count:
            if tokens[j].kind == "punct" and tokens[j].value == "{":
                local += 1
            elif tokens[j].kind == "punct" and tokens[j].value == "}":
                local -= 1
                if local == 0:
                    break
            j += 1
        j += 1
        if not (j + 1 < count and _is(tokens[j], "ident", "from") and tokens[j + 1].kind == "string"):
            return None
        return JsReference("static", tokens[j + 1].value, line, type_only)
    # export * [as ns] from 'x'
    for offset in range(1, 4):
        if j + offset + 1 < count and _is(tokens[j + offset], "ident", "from") \
                and tokens[j + offset + 1].kind == "string":
            return JsReference("static", tokens[j + offset + 1].value, line, type_only)
    return None


# ---------------------------------------------------------------- intake

_NODE_BUILTIN = re.compile(r"node:[A-Za-z0-9_/.-]+")
_SCOPED = re.compile(r"(@[A-Za-z0-9][A-Za-z0-9._~-]*/[A-Za-z0-9._~-]+)(?:/.*)?", re.S)
_PACKAGE = re.compile(r"([A-Za-z0-9_$][A-Za-z0-9._$~-]*)(?:/.*)?", re.S)


def classify_specifier(spec: str) -> tuple[str, str]:
    """Return (``relative`` | ``external`` | ``unresolved``, normalised name)."""
    if spec in {".", ".."} or spec.startswith(("./", "../")):
        return "relative", spec
    if _NODE_BUILTIN.fullmatch(spec):
        return "external", spec
    scoped = _SCOPED.fullmatch(spec)
    if scoped:
        return "external", scoped.group(1)
    package = _PACKAGE.fullmatch(spec)
    if package:
        return "external", package.group(1)
    return "unresolved", spec


def resolve_relative(spec: str, from_path: str, files: set[str]) -> tuple[str | None, bool]:
    """Resolve a relative specifier to an observed file. Returns (path, ambiguous).

    Stages, first stage with any hit wins: exact path (``./a.js`` may map to
    ``a.ts``/``a.tsx``), path + extension, ``/index`` + extension. More than one
    hit in a stage is ambiguous and is never guessed.
    """
    base = posixpath.normpath(posixpath.join(posixpath.dirname(from_path), spec))
    if base == ".":
        base = ""
    if base == ".." or base.startswith("../"):
        return None, False
    directory_only = spec.endswith("/") or spec in {".", ".."}
    stages: list[list[str]] = []
    if not directory_only:
        exact = [base] if base in files else []
        if not exact:
            suffix = PurePosixPath(base).suffix
            stem = base[:len(base) - len(suffix)] if suffix else base
            exact = [stem + alt for alt in _TS_COUNTERPARTS.get(suffix, ()) if stem + alt in files]
        stages.append(exact)
        stages.append([base + ext for ext in JS_SUFFIXES if base + ext in files])
    stages.append([posixpath.join(base, "index" + ext) for ext in JS_SUFFIXES
                   if posixpath.join(base, "index" + ext) in files])
    for hits in stages:
        if len(hits) == 1:
            return hits[0], False
        if len(hits) > 1:
            return None, True
    return None, False


def is_js_candidate(path: str) -> bool:
    """Allowlisted JS/TS file that intake analyses (declarations/minified/tests excluded)."""
    name = PurePosixPath(path).name.lower()
    if not name.endswith(JS_SUFFIXES):
        return False
    if re.search(r"\.d\.(?:ts|mts|cts)$", name) or re.search(r"\.min\.[^.]+$", name):
        return False
    return not re.search(r"\.(?:test|spec)\.[^.]+$", name)


def _id(prefix: str, key: str) -> str:
    return prefix + hashlib.sha256(key.encode("utf-8")).hexdigest()[:14]


def _module(path: str) -> str:
    return str(PurePosixPath(path).with_suffix(""))


def _clean_spec(spec: str) -> bool:
    return 0 < len(spec) <= MAX_SPECIFIER_CHARS and not any(ord(c) < 32 or ord(c) == 127 for c in spec)


def prepare_js_project_intake(
    project_root, *, system: str, goal: str, requirements: list[str],
    max_modules: int, max_files: int, max_file_bytes: int,
    exclude: list[str] | None = None,
):
    """Lexical JS/TS intake. Called by ``prepare_project_intake(language='javascript')``."""
    from .project_intake import (  # local import: project_intake imports this module lazily
        IntakeObservations, IntakeResult, ModuleObservation, _is_excluded, _make_brief,
        apply_exclusions,
    )
    from pathlib import Path

    root = Path(project_root)
    inventory = scan_sources(root, max_files=max_files, max_bytes=max_file_bytes)
    selected = [x for x in inventory.files if x.kind == "source" and is_js_candidate(x.path)]
    selected = apply_exclusions(selected, [f.path for f in inventory.files], exclude)
    if not selected:
        raise ValueError(
            "No JavaScript/TypeScript source modules found. This intake supports "
            ".js .jsx .mjs .cjs .ts .tsx files in the shared source allowlist only."
        )
    if len(selected) > max_modules:
        raise ValueError(
            f"Found {len(selected)} JavaScript/TypeScript modules, exceeding "
            f"--max-modules={max_modules}; choose a smaller subtree or increase the limit."
        )
    by_module = {_module(f.path): f for f in selected}
    if len(by_module) != len(selected):
        raise ValueError("Ambiguous JavaScript/TypeScript module names; select a narrower source directory")
    files = {f.path: f for f in selected}
    file_set = set(files)
    ids = {f.path: _id("mod_", f.path) for f in selected}
    if len(set(ids.values())) != len(ids):
        raise ValueError("Hashed component ID collision")
    scans: dict[str, JsScan] = {}
    for file in selected:
        data = read_safe_source_bytes(root, file.path, byte_limit=max_file_bytes)
        if hashlib.sha256(data).hexdigest() != file.sha256:
            raise ValueError(f"File changed during scanning: {file.path}")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError(f"Cannot safely decode JavaScript/TypeScript module {file.path}") from None
        scans[file.path] = scan_js_source(text)

    brief = _make_brief(system, goal, requirements, len(selected))
    root_component = Component(
        id="system", name=brief.system,
        responsibility="Provisional grouping of JavaScript/TypeScript source modules for owner review.",
        boundary="Draft documentation scope; no deployment boundary was observed.",
        assumptions=[
            "The source-module grouping may not match true architectural responsibilities.",
            "User-provided requirements are not mapped automatically to implementation.",
        ],
        status="proposed",
    )
    proposals: list[ComponentProposal] = []
    observations: list[ModuleObservation] = []
    claims: list[SourceClaim] = []
    edges_by_source: dict[str, dict[str, dict]] = {}
    for path in sorted(files):
        file = files[path]
        name = _module(path)
        scan = scans[path]
        anomalies = scan.anomalies
        external: set[str] = set()
        unresolved: set[str] = set()
        nonliteral = 0
        targets: dict[str, dict] = {}
        for ref in scan.references:
            if ref.specifier is None:
                nonliteral += 1
                continue
            if not _clean_spec(ref.specifier):
                anomalies += 1
                continue
            category, label = classify_specifier(ref.specifier)
            if category == "external":
                external.add(label)
            elif category == "unresolved":
                unresolved.add(ref.specifier)
            else:
                target, _ambiguous = resolve_relative(ref.specifier, path, file_set)
                if target is None:
                    unresolved.add(ref.specifier)
                elif target != path:
                    info = targets.setdefault(target, {
                        "line": ref.line, "kinds": set(), "all_type_only": True, "dynamic": False})
                    info["line"] = min(info["line"], ref.line)
                    if ref.kind == "static":
                        info["kinds"].add("type-only import" if ref.type_only else "static import")
                    else:
                        info["kinds"].add("require()" if ref.kind == "require" else "dynamic import()")
                        info["dynamic"] = True
                    if not (ref.kind == "static" and ref.type_only):
                        info["all_type_only"] = False
        edges_by_source[path] = targets
        internal = sorted(_module(t) for t in targets)
        observations.append(ModuleObservation(
            component_id=ids[path], module=name, source_path=path, sha256=file.sha256,
            functions=scan.functions[:MAX_SYMBOLS], classes=scan.classes[:MAX_SYMBOLS],
            symbols_omitted=max(0, len(scan.functions) - MAX_SYMBOLS)
            + max(0, len(scan.classes) - MAX_SYMBOLS),
            internal_imports=internal,
            variables=scan.variables[:MAX_SYMBOLS],
            variables_omitted=max(0, len(scan.variables) - MAX_SYMBOLS),
            external_imports=sorted(external),
            unresolved_imports=sorted(unresolved),
            type_only_imports=sorted(_module(t) for t, i in targets.items() if i["all_type_only"]),
            dynamic_imports=sorted(_module(t) for t, i in targets.items() if i["dynamic"]),
            nonliteral_dynamic_references=nonliteral,
            ambiguous_slashes=scan.ambiguous_slashes,
            lexical_anomalies=anomalies,
        ))
        proposals.append(ComponentProposal(
            id=ids[path], name="JS/TS module " + name,
            responsibility=f"Candidate module boundary for {name}; business role unverified.",
            boundary=f"Observed JavaScript/TypeScript file {path}, not a verified runtime service boundary.",
            rationale="Observed module declaration is a structural proposal; owner must assess grouping.",
            assumptions=["Lexical import references do not confirm actual runtime interactions."],
            risks=["Interfaces, data ownership, and requirement coverage are not yet documented."],
        ))
        claims.append(SourceClaim(
            architecture_id=ids[path], source_path=path, sha256=file.sha256,
            assertion=f"Lexically scanned JavaScript/TypeScript module {name} at this path; semantic role unknown.",
            basis="observed",
            line_start=1 if file.line_count else None,
            line_end=1 if file.line_count else None,
        ))
    edges = []
    for path in sorted(files):
        for target_path in sorted(edges_by_source[path]):
            info = edges_by_source[path][target_path]
            rel_id = _id("dep_", path + "\0" + target_path)
            edges.append(Relationship(
                id=rel_id, source_id=ids[path], target_id=ids[target_path], kind="dependency",
                description=(
                    f"Lexical import reference ({', '.join(sorted(info['kinds']))}) from "
                    f"{_module(path)} to {_module(target_path)}; could be conditional or "
                    "type-only and is not a verified runtime call."
                ),
            ))
            claims.append(SourceClaim(
                architecture_id=rel_id, source_path=path, sha256=files[path].sha256,
                assertion=f"Lexical import reference names module {_module(target_path)}.",
                basis="observed", line_start=info["line"], line_end=info["line"],
            ))
    if len({edge.id for edge in edges}) != len(edges):
        raise ValueError("Hashed dependency ID collision")
    fixture = FixtureDesign(
        root=root_component, proposals_by_parent={"system": proposals}, relationships=edges,
    )
    report = IntakeObservations(
        method="javascript_lexical_imports",
        modules=observations, dependencies=edges,
        excluded_non_python_source=[
            f.path for f in inventory.files
            if f.kind in {"source", "schema"} and f.path not in files
            and not _is_excluded(f.path, exclude)
        ],
        skipped_oversized_files=inventory.skipped_oversized,
        excluded_by_request=exclude,
        limitations=JS_LIMITATIONS,
    )
    return IntakeResult(
        brief=brief, fixture=fixture, evidence=SourceEvidence(claims=claims),
        inventory=inventory, observations=report, language="javascript",
    )


JS_LIMITATIONS = [
    "No application source was imported, run, tested, bundled, transpiled or sent to a model.",
    "Lexical import references do not establish actual runtime calls; they may be conditional, "
    "type-only or dead code.",
    "Module boundaries are candidate components, not certified architecture.",
    "Functional requirements are user-supplied and not mapped automatically.",
    "Interfaces, owned data, style, and implementation verification remain unknown.",
    "Source hash matches prove file-byte equality, not semantic correctness.",
    "Only allowlisted bounded .js .jsx .mjs .cjs .ts .tsx files were analyzed; .d.ts "
    "declaration files, *.min.* bundles, *.test.* / *.spec.* files and .mts/.cts files "
    "(not in the shared inventory allowlist) are not analyzed.",
    "Bare specifiers (react, @scope/pkg, node:fs) are listed as external package names, never "
    "as edges. tsconfig/jsconfig paths and baseUrl aliases and package.json exports/imports/"
    "main fields are not resolved, so an alias such as @/utils or src/utils is shown as "
    "unresolved or as an external package name.",
    "Relative specifiers resolve only to observed files (exact, +extension, /index); an "
    "unresolved or ambiguous relative specifier is recorded, never guessed.",
    "require()/import() with a non-literal argument, require.resolve, jest.mock and similar "
    "calls, and imports inside template-literal expressions are not resolved.",
    "The lexer is not a parser: regex-versus-division is a heuristic and JSX, decorators and "
    "framework conventions are not interpreted.",
]


def render_js_report(result) -> str:
    from .project_intake import _md

    obs = result.observations
    mods = obs.modules
    type_only = sum(len(m.type_only_imports or []) for m in mods)
    ext_names = {x for m in mods for x in (m.external_imports or [])}
    unresolved = sum(len(m.unresolved_imports or []) for m in mods)
    nonliteral = sum(m.nonliteral_dynamic_references or 0 for m in mods)
    anomalies = sum(m.lexical_anomalies or 0 for m in mods)
    ambiguous = sum(m.ambiguous_slashes or 0 for m in mods)
    lines = [
        "# Provisional JavaScript/TypeScript project architecture intake",
        "",
        "> Owner review required. This report records lexical, syntax-level module/import "
        "observations and candidate boundaries. No code was executed and no "
        "business architecture, security, or production behavior was verified.",
        "",
        "## Supplied project intent",
        "",
        "- System: " + _md(result.brief.system),
        "- Goal: " + _md(result.brief.goals[0]),
        f"- User-supplied requirements: {len(result.brief.functional_requirements)}",
        "",
        "## Static analysis",
        "",
        f"- Modules scanned: {len(mods)}",
        f"- Import dependencies detected (edges between observed modules): {len(obs.dependencies)}",
        f"- Edge targets referenced only through import type / export type: {type_only}",
        f"- Distinct external package names referenced (not edges): {len(ext_names)}",
        f"- Unresolved relative or non-package specifiers: {unresolved}",
        f"- Non-literal require()/import() references (not resolved): {nonliteral}",
        f"- Lexer recoveries (unterminated or oversized constructs): {anomalies}",
        f"- Slashes the regex heuristic could not decide (after ) or }}): {ambiguous}",
        f"- Other allowlisted source/schema files NOT analyzed: {len(obs.excluded_non_python_source)}",
        f"- Oversized inventory files skipped: {obs.skipped_oversized_files}",
        *([f"- Excluded by request (--exclude): {', '.join(_md(p) for p in obs.excluded_by_request)}"]
          if obs.excluded_by_request else []),
        "",
        "| Component ID | Module | Project-relative file | Top-level symbols | Internal imports |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in mods:
        names = item.functions + item.classes + (item.variables or [])
        symbols = ", ".join(names) or "None"
        omitted = item.symbols_omitted + (item.variables_omitted or 0)
        if omitted:
            symbols += f" ({omitted} more names omitted)"
        values = [item.component_id, item.module, item.source_path, symbols,
                  ", ".join(item.internal_imports) or "None"]
        lines.append("| " + " | ".join(_md(x) for x in values) + " |")
    lines.extend(["", "## External packages referenced (names only, not edges)", ""])
    lines += [f"- {_md(m.module)}: {_md(', '.join(m.external_imports))}"
              for m in mods if m.external_imports] or ["None."]
    lines.extend(["", "## Unresolved references", ""])
    lines += [f"- {_md(m.module)}: {_md(', '.join(m.unresolved_imports))}"
              for m in mods if m.unresolved_imports] or ["None."]
    lines.extend(["", "## Lexical caveats", ""])
    caveats = []
    for m in mods:
        parts = []
        if m.nonliteral_dynamic_references:
            parts.append(f"{m.nonliteral_dynamic_references} non-literal require()/import()")
        if m.ambiguous_slashes:
            parts.append(f"{m.ambiguous_slashes} undecidable slash(es)")
        if m.lexical_anomalies:
            parts.append(f"{m.lexical_anomalies} lexer recovery(ies)")
        if parts:
            caveats.append(f"- {_md(m.source_path)}: " + _md("; ".join(parts)))
    lines += caveats or ["None recorded."]
    lines.extend(["", "## Other allowlisted source files NOT analyzed", ""])
    lines += ["- " + _md(x) for x in obs.excluded_non_python_source] or [
        "No other source/schema files were identified in the inventory."
    ]
    lines.extend(["", "## Human and Claude Code review checklist", "",
        "- [ ] Confirm module boundaries represent useful architecture components.",
        "- [ ] Confirm roles, user actors, and business requirements with the owner.",
        "- [ ] Map real requirements to the correct source-backed components.",
        "- [ ] Analyze interfaces, data ownership, runtime behavior, external dependencies.",
        "- [ ] Add appropriate architecture style choices, decisions and quality scenarios.",
        "- [ ] Check unresolved specifiers, path aliases, non-literal require()/import() and lexical caveats.",
        "- [ ] Run design, review and document with this draft and its source map.",
        "- [ ] Preserve unverified statuses; do not invent completed tests or expert reviews.",
        "", "## Research and evidence limitations", "",
    ])
    lines.extend("- " + _md(x) for x in obs.limitations)
    return "\n".join(lines) + "\n"
