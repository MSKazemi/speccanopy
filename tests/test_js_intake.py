"""Offline JavaScript/TypeScript lexical intake.

Every project here is a synthetic temporary tree. Nothing is executed: no Node,
no target code, no network. Files that would write a marker if run are used to
prove that intake never runs source.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from speccanopy.cli import main
from speccanopy.js_intake import scan_js_source
from speccanopy.models import ArchitectureSpec
from speccanopy.project_intake import IntakeObservations, prepare_project_intake
from speccanopy.source_evidence import SourceEvidence, SourceInventory, assess_sources
from speccanopy.structure_diff import compare_module_observations, load_module_observations

ARTIFACTS = {
    "brief.json", "design.json", "source-evidence.json",
    "source-inventory.json", "module-observations.json", "intake-review.md",
}


def _tree(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _intake(root: Path, **kwargs):
    return prepare_project_intake(
        root, system="Demo", goal="Document modules",
        requirements=["The app must do a thing"], language="javascript", **kwargs,
    )


def _modules(result):
    return {m.module: m for m in result.observations.modules}


def _edges(result):
    by_id = {m.component_id: m.module for m in result.observations.modules}
    return {(by_id[e.source_id], by_id[e.target_id]) for e in result.observations.dependencies}


def _refs(text: str):
    scan = scan_js_source(text)
    return [(r.kind, r.specifier, r.type_only) for r in scan.references]


# --------------------------------------------------------------- lexer level


def test_static_imports_reexports_and_side_effect_imports():
    text = (
        "import a from './a';\n"
        "import { b, c as d } from \"./b\";\n"
        "import * as e from './e'\n"
        "import './side';\n"
        "export * from './f';\n"
        "export * as g from './g';\n"
        "export { h } from './h';\n"
        "export { local };\n"
        "import def, { x } from './def';\n"
    )
    assert _refs(text) == [
        ("static", "./a", False), ("static", "./b", False), ("static", "./e", False),
        ("static", "./side", False), ("static", "./f", False), ("static", "./g", False),
        ("static", "./h", False), ("static", "./def", False),
    ]


def test_type_only_imports_and_exports_are_flagged_not_dropped():
    text = (
        "import type { A } from './types';\n"
        "import type B from './b';\n"
        "export type { C } from './c';\n"
        "import type from './type-named-default';\n"
        "import { type D, E } from './mixed';\n"
    )
    assert _refs(text) == [
        ("static", "./types", True), ("static", "./b", True), ("static", "./c", True),
        ("static", "./type-named-default", False), ("static", "./mixed", False),
    ]


def test_require_and_dynamic_import_literals_and_nonliterals():
    text = (
        "const fs = require('fs');\n"
        "const lazy = () => import('./lazy');\n"
        "const second = require(\"./second\");\n"
        "const bad = require(name);\n"
        "const bad2 = import(`./tpl/${x}`);\n"
        "const bad3 = require('./a' + suffix);\n"
        "if (x) { require('./nested'); }\n"
    )
    assert _refs(text) == [
        ("require", "fs", False), ("dynamic", "./lazy", False), ("require", "./second", False),
        ("require", None, False), ("dynamic", None, False), ("require", None, False),
        ("require", "./nested", False),
    ]


def test_member_access_named_require_or_import_is_not_a_reference():
    text = "obj.require('./x'); obj.import('./y'); x?.require('./z'); import.meta.url;\n"
    assert _refs(text) == []


def test_ts_import_equals_require_is_a_require_reference():
    assert _refs("import fs = require('./fs-shim');\n") == [("require", "./fs-shim", False)]


@pytest.mark.parametrize("text", [
    "// import a from './a'\n",
    "/* import a from './a' */\n",
    "// require('./a')\n",
    "const x = 1; // require(\"pkg\") and import('./b')\n",
    "/require('a')/.test(s);\n",
    "function require(name) { return name; }\n",
    "class K { import(x) {} }\nconst o = { require: 1 };\n",
    "/* multi\n   line require('./a')\n*/\n",
    "const s = \"import a from './a'\";\n",
    "const s = 'require(\"./a\")';\n",
    "const s = `import ${x} from './b'`;\n",
    "const s = `outer ${ `inner ${ require('./c') }` } tail`;\n",
    "const r = /import x from 'y'/;\n",
    "const r = /require\\('.\\/a'\\)/g;\n",
    "const r = /[/]import x from 'y'/;\n",
    "const x = a / b; // import z from './z'\n",
    "const s = 'it\\'s import a from \"./a\"';\n",
])
def test_references_inside_comments_strings_templates_and_regexes_are_not_counted(text):
    assert _refs(text) == []


def test_code_after_each_skipped_construct_is_still_scanned():
    text = (
        "// c\nimport a from './a';\n"
        "/* c */ import b from './b';\n"
        "const s = 'x'; import c from './c';\n"
        "const t = `y${1}`; import d from './d';\n"
        "const r = /re/g; import e from './e';\n"
        "const q = 4 / 2 / 1; import f from './f';\n"
    )
    assert [r[1] for r in _refs(text)] == ["./a", "./b", "./c", "./d", "./e", "./f"]


def test_division_is_not_mistaken_for_a_regex_after_values():
    text = (
        "const a = 10 / 2; const b = a / 3; const c = (a) / 2; const d = [1][0] / 2;\n"
        "import x from './x';\n"
        "const e = 8 /2/ 4;\n"
    )
    assert _refs(text) == [("static", "./x", False)]


def test_keyword_used_as_property_name_is_a_value_so_slash_is_division():
    text = "const a = obj.return / 2; const b = require('pkg'); const c = obj.in / 3;\n"
    assert _refs(text) == [("require", "pkg", False)]
    scan = scan_js_source("const a = obj.return / 2 / 3;\nconst s = 'it\\'s';\n")
    assert scan.anomalies == 0


def test_regex_after_keywords_and_operators():
    text = (
        "function f() { return /require\\('.\\/a'\\)/.test(s); }\n"
        "const m = x ? /import a from 'a'/ : /b/;\n"
        "import ok from './ok';\n"
    )
    assert _refs(text) == [("static", "./ok", False)]


def test_ambiguous_slashes_after_close_paren_or_brace_are_counted():
    scan = scan_js_source("const a = (1) / 2;\nif (x) /re/.test(y);\n")
    assert scan.ambiguous_slashes == 2
    assert scan_js_source("const a = 1 / 2;\n").ambiguous_slashes == 0


def test_jsx_closing_tags_do_not_swallow_following_imports():
    text = "const el = <div>hi</div>;\nimport a from './a';\n"
    assert _refs(text) == [("static", "./a", False)]


def test_unterminated_constructs_are_recovered_and_counted_not_fatal():
    assert scan_js_source("const s = 'oops\nimport a from './a';\n").anomalies >= 1
    assert [r.specifier for r in scan_js_source("const s = 'oops\nimport a from './a';\n").references] == ["./a"]
    assert scan_js_source("/* never closed\n").anomalies == 1
    assert scan_js_source("const t = `never closed ${\n").anomalies >= 1


def test_deeply_nested_template_does_not_raise_recursion_error():
    text = "const t = " + "`${" * 5000 + "x" + "}`" * 5000 + ";\n"
    scan = scan_js_source(text)
    assert scan.anomalies >= 1


def test_line_numbers_are_one_based_and_survive_multiline_tokens():
    text = "/* a\nb */\nconst s = `x\ny`;\n\nimport a from './a';\n"
    assert [r.line for r in scan_js_source(text).references] == [6]


def test_top_level_declarations_only():
    text = (
        "function top() {}\n"
        "async function asyncTop() {}\n"
        "function* gen() {}\n"
        "export function exp() {}\n"
        "export default function defFn() {}\n"
        "class Klass { method() { function inner() {} } }\n"
        "export class Exported {}\n"
        "export abstract class Abs {}\n"
        "export default class DefaultKlass {}\n"
        "interface Iface { m(): void }\n"
        "export interface PubIface {}\n"
        "type Alias = string;\n"
        "export type Generic<T> = T[];\n"
        "enum Color { Red }\n"
        "export const enum Flags { A }\n"
        "const one = 1, two = 2;\n"
        "export let lets = 0;\n"
        "var old = 1;\n"
        "export const fn = () => { function nestedInArrow() {} };\n"
        "foo(function notTop() {});\n"
        "const g = function expr() {};\n"
        "if (x) { function blockFn() {} }\n"
    )
    scan = scan_js_source(text)
    assert scan.functions == ["top", "asyncTop", "gen", "exp", "defFn"]
    assert scan.classes == [
        "Klass", "Exported", "Abs", "DefaultKlass", "Iface", "PubIface",
        "Alias", "Generic", "Color", "Flags",
    ]
    assert scan.variables == ["one", "lets", "old", "fn", "g"]


def test_type_and_interface_are_only_declarations_in_declaration_position():
    text = "const type = 1;\nlet interface_ = 2;\nfoo.type = 3;\ntype\n"
    scan = scan_js_source(text)
    assert scan.classes == []


def test_declaration_after_asi_newline_is_recognised_without_semicolon():
    text = "const a = 1\nfunction after() {}\nconst b = 2\nclass K {}\n"
    scan = scan_js_source(text)
    assert scan.functions == ["after"]
    assert scan.classes == ["K"]


# ------------------------------------------------------------ intake level


def test_esm_project_modules_edges_and_extension_resolution(tmp_path):
    root = _tree(tmp_path / "app", {
        "src/index.js": "import { api } from './api/index.js';\nimport util from './util';\n",
        "src/api/index.js": "import { svc } from '../service.mjs';\nexport const api = 1;\n",
        "src/service.mjs": "export const svc = 1;\n",
        "src/util.js": "export default function util() {}\n",
    })
    result = _intake(root)
    assert set(_modules(result)) == {"src/index", "src/api/index", "src/service", "src/util"}
    assert _edges(result) == {
        ("src/index", "src/api/index"), ("src/index", "src/util"),
        ("src/api/index", "src/service"),
    }
    assert result.observations.method == "javascript_lexical_imports"
    assert _modules(result)["src/util"].functions == ["util"]


def test_directory_index_and_extension_precedence(tmp_path):
    root = _tree(tmp_path / "app", {
        "main.ts": "import a from './lib';\nimport b from './only-dir';\nimport c from './both';\n",
        "lib.ts": "export default 1;\n",
        "lib/index.ts": "export default 2;\n",
        "only-dir/index.tsx": "export default 3;\n",
        "both/index.js": "export default 4;\n",
    })
    result = _intake(root)
    # file with extension wins over a directory index; index resolution works
    assert _edges(result) == {
        ("main", "lib"), ("main", "only-dir/index"), ("main", "both/index"),
    }


def test_ts_js_extension_maps_to_ts_source_and_other_mappings_are_unresolved(tmp_path):
    root = _tree(tmp_path / "app", {
        "main.ts": "import a from './a.js';\nimport c from './c.js';\nimport d from './d.ts';\n",
        "a.ts": "export default 1;\n",
        "c.jsx": "export default 1;\n",
        "d.ts": "export default 1;\n",
    })
    result = _intake(root)
    main_mod = _modules(result)["main"]
    assert _edges(result) == {("main", "a"), ("main", "d")}
    # ./c.js with only c.jsx present: not a documented mapping -> unresolved
    assert main_mod.unresolved_imports == ["./c.js"]


def test_resolver_does_not_choose_between_two_candidates():
    from speccanopy.js_intake import resolve_relative
    assert resolve_relative("./b", "m.ts", {"m.ts", "b.ts", "b.tsx"}) == (None, True)
    assert resolve_relative("./d", "m.ts", {"m.ts", "d/index.ts", "d/index.js"}) == (None, True)
    assert resolve_relative("./b", "m.ts", {"m.ts", "b.ts"}) == ("b.ts", False)
    assert resolve_relative("../x", "m.ts", {"m.ts"}) == (None, False)
    assert resolve_relative(".", "sub/m.ts", {"sub/m.ts", "sub/index.ts"}) == ("sub/index.ts", False)


def test_unresolved_relative_is_recorded_not_guessed(tmp_path):
    root = _tree(tmp_path / "app", {
        "a.js": "import x from './missing';\nimport y from '../../outside';\n"
                "import css from './style.css';\nimport z from '/abs/path';\n",
    })
    result = _intake(root)
    assert result.observations.dependencies == []
    assert _modules(result)["a"].unresolved_imports == [
        "../../outside", "./missing", "./style.css", "/abs/path",
    ]
    assert _modules(result)["a"].internal_imports == []


def test_bare_scoped_and_node_specifiers_are_external_not_edges(tmp_path):
    root = _tree(tmp_path / "app", {
        "a.ts": (
            "import React from 'react';\n"
            "import { x } from '@scope/pkg/sub/path';\n"
            "import fs from 'node:fs';\n"
            "import fp from 'lodash/fp';\n"
            "const p = require('path');\n"
            "import('chalk');\n"
        ),
        "react.js": "export default 1;\n",
    })
    result = _intake(root)
    mod = _modules(result)["a"]
    assert result.observations.dependencies == []
    assert mod.external_imports == ["@scope/pkg", "chalk", "lodash", "node:fs", "path", "react"]
    assert mod.unresolved_imports == []


def test_tsconfig_aliases_and_package_json_exports_are_not_resolved(tmp_path):
    root = _tree(tmp_path / "app", {
        "tsconfig.json": json.dumps({"compilerOptions": {"paths": {"@/*": ["src/*"]}}}),
        "src/a.ts": "import b from '@/b';\nimport c from '~/c';\nimport d from '#internal/d';\n",
        "src/b.ts": "export default 1;\n",
    })
    result = _intake(root)
    assert result.observations.dependencies == []
    assert _modules(result)["src/a"].unresolved_imports == ["#internal/d", "@/b", "~/c"]


def test_type_only_and_dynamic_edges_are_distinguished(tmp_path):
    root = _tree(tmp_path / "app", {
        "a.ts": (
            "import type { T } from './types';\n"
            "import { v } from './value';\n"
            "const l = () => import('./lazy');\n"
            "const r = require('./legacy');\n"
            "import type { U } from './mixed';\n"
            "import { w } from './mixed';\n"
            "const n = require(x); const m = import(y);\n"
        ),
        "types.ts": "export type T = 1;\n",
        "value.ts": "export const v = 1;\n",
        "lazy.ts": "export {};\n",
        "legacy.js": "module.exports = 1;\n",
        "mixed.ts": "export type U = 1; export const w = 1;\n",
    })
    mod = _modules(_intake(root))["a"]
    assert mod.internal_imports == ["lazy", "legacy", "mixed", "types", "value"]
    assert mod.type_only_imports == ["types"]
    assert mod.dynamic_imports == ["lazy", "legacy"]
    assert mod.nonliteral_dynamic_references == 2


def test_self_import_is_not_an_edge(tmp_path):
    root = _tree(tmp_path / "app", {"a.js": "import me from './a';\n"})
    assert _modules(_intake(root))["a"].internal_imports == []


def test_reexport_and_cjs_edges(tmp_path):
    root = _tree(tmp_path / "app", {
        "index.js": "export * from './a';\nexport { b } from './b.cjs';\n",
        "a.js": "const b = require('./b.cjs');\nmodule.exports = { b };\n",
        "b.cjs": "module.exports = 1;\n",
    })
    assert _edges(_intake(root)) == {("index", "a"), ("index", "b"), ("a", "b")}


def test_excluded_files_are_not_modules_but_are_listed(tmp_path):
    root = _tree(tmp_path / "app", {
        "src/app.ts": "import t from './types';\nimport m from './vendor.min';\n",
        "src/types.d.ts": "export type T = 1;\n",
        "src/vendor.min.js": "import q from './app';\n",
        "src/app.test.ts": "import a from './app';\n",
        "src/app.spec.js": "import a from './app';\n",
        "tests/app.js": "import a from '../src/app';\n",
        "src/__tests__/x.js": "export {};\n",
        "node_modules/dep/index.js": "export {};\n",
        "dist/bundle.js": "export {};\n",
        "build/out.js": "export {};\n",
        "coverage/lcov.js": "export {};\n",
        ".hidden/h.js": "export {};\n",
        "script.py": "import os\n",
    })
    result = _intake(root)
    assert set(_modules(result)) == {"src/app"}
    excluded = set(result.observations.excluded_non_python_source)
    assert {"src/types.d.ts", "src/vendor.min.js", "src/app.test.ts",
            "src/app.spec.js", "script.py"} <= excluded
    assert not any(p.startswith(("node_modules", "dist", "build", "coverage", ".hidden"))
                   for p in excluded)
    mod = _modules(result)["src/app"]
    assert sorted(mod.unresolved_imports) == ["./types", "./vendor.min"]


def test_privacy_exclusions_apply(tmp_path):
    root = _tree(tmp_path / "app", {
        "src/a.js": "export const a = 1;\n",
        ".env": "TOKEN=SECRET_MARKER\n",
        "secrets/keys.js": "export const k = 'SECRET_MARKER';\n",
        "private/p.js": "export const p = 1;\n",
        "src/password-store.js": "export const x = 'SECRET_MARKER';\n",
    })
    folder = tmp_path / "out"
    assert main([
        "project-intake", str(root), "--language", "javascript", "--system", "S",
        "--goal", "G", "--requirement", "R", "--output", str(folder),
    ]) == 0
    assert set(_modules(_intake(root))) == {"src/a"}
    assert "SECRET_MARKER" not in "".join(p.read_text() for p in folder.iterdir())
    assert "secrets/" not in (folder / "source-inventory.json").read_text()


def test_bounds_module_limit_files_limit_and_empty_project(tmp_path):
    root = _tree(tmp_path / "app", {f"m{i}.js": "export {};\n" for i in range(4)})
    with pytest.raises(ValueError, match="exceeding --max-modules=3"):
        _intake(root, max_modules=3)
    with pytest.raises(ValueError, match="max_modules"):
        _intake(root, max_modules=51)
    with pytest.raises(ValueError, match="file limit"):
        _intake(root, max_files=2)
    empty = _tree(tmp_path / "empty", {"README.md": "x"})
    with pytest.raises(ValueError, match="No JavaScript/TypeScript source modules"):
        _intake(empty)


def test_oversized_files_are_skipped_and_counted(tmp_path):
    root = _tree(tmp_path / "app", {"small.js": "export {};\n", "big.js": "x" * 500})
    result = _intake(root, max_file_bytes=100)
    assert set(_modules(result)) == {"small"}
    assert result.observations.skipped_oversized_files == 1


def test_ambiguous_module_names_fail_closed(tmp_path):
    root = _tree(tmp_path / "app", {"a.js": "export {};\n", "a.ts": "export {};\n"})
    with pytest.raises(ValueError, match="Ambiguous"):
        _intake(root)


def test_invalid_utf8_fails_closed(tmp_path):
    root = tmp_path / "app"
    root.mkdir()
    (root / "a.js").write_bytes(b"\xff\xfe\xfa")
    with pytest.raises(ValueError, match="a.js"):
        _intake(root)


def test_utf8_bom_and_hashbang_are_handled(tmp_path):
    root = tmp_path / "app"
    root.mkdir()
    (root / "cli.js").write_bytes(b"\xef\xbb\xbf#!/usr/bin/env node\nimport a from './a.js';\n")
    (root / "a.js").write_text("export {};\n")
    assert _edges(_intake(root)) == {("cli", "a")}


def test_symbols_are_capped_like_python_intake(tmp_path):
    body = "".join(f"function f{i}() {{}}\n" for i in range(35))
    body += "".join(f"class C{i} {{}}\n" for i in range(32))
    body += "".join(f"const v{i} = 1;\n" for i in range(33))
    root = _tree(tmp_path / "app", {"a.js": body})
    mod = _modules(_intake(root))["a"]
    assert len(mod.functions) == 30 and len(mod.classes) == 30
    assert mod.symbols_omitted == 5 + 2
    assert len(mod.variables) == 30 and mod.variables_omitted == 3


def test_lexical_diagnostics_are_recorded_and_surfaced_in_the_review(tmp_path):
    root = _tree(tmp_path / "app", {
        "a.js": "const a = (1) / 2;\nconst s = 'oops\n",
        "b.js": "export {};\n",
    })
    result = _intake(root)
    mod = _modules(result)["a"]
    assert mod.ambiguous_slashes == 1 and mod.lexical_anomalies == 1
    folder = tmp_path / "out"
    assert main(["project-intake", str(root), "--language", "javascript", "--system", "S",
                 "--goal", "G", "--requirement", "R", "--output", str(folder)]) == 0
    review = (folder / "intake-review.md").read_text()
    assert "Lexical caveats" in review
    assert "a.js" in review.split("Lexical caveats", 1)[1]


def test_review_lists_externals_unresolved_and_limits(tmp_path):
    root = _tree(tmp_path / "app", {
        "a.ts": "import r from 'react';\nimport m from './missing';\nrequire(dyn);\n",
    })
    folder = tmp_path / "out"
    assert main(["project-intake", str(root), "--language", "javascript", "--system", "S",
                 "--goal", "G", "--requirement", "R", "--output", str(folder)]) == 0
    review = (folder / "intake-review.md").read_text()
    assert "# Provisional JavaScript/TypeScript project architecture intake" in review
    assert "Owner review required" in review
    assert "react" in review and "./missing" in review
    assert "not resolved" in review.lower() or "not resolve" in review.lower()
    assert "tsconfig" in review
    assert "Non-literal" in review


def test_artifacts_schema_valid_and_claims_are_observed_and_hash_bound(tmp_path):
    root = _tree(tmp_path / "app", {
        "src/a.ts": "import b from './b';\nexport function run() {}\n",
        "src/b.ts": "export class B {}\n",
    })
    folder = tmp_path / "out"
    assert main(["project-intake", str(root), "--language", "javascript", "--system", "S",
                 "--goal", "G", "--requirement", "R", "--output", str(folder)]) == 0
    assert {p.name for p in folder.iterdir()} == ARTIFACTS
    obs = IntakeObservations.model_validate_json((folder / "module-observations.json").read_text())
    evidence = SourceEvidence.model_validate_json((folder / "source-evidence.json").read_text())
    inventory = SourceInventory.model_validate_json((folder / "source-inventory.json").read_text())
    assert obs.method == "javascript_lexical_imports"
    assert len(evidence.claims) == 2 + 1
    assert all(c.basis == "observed" for c in evidence.claims)
    assert {c.source_path for c in evidence.claims} <= {f.path for f in inventory.files}
    edge_claim = [c for c in evidence.claims if c.line_start == 1 and c.source_path == "src/a.ts"
                  and "import reference" in c.assertion]
    assert len(edge_claim) == 1
    assert "Lexical" in obs.dependencies[0].description


def test_output_is_deterministic(tmp_path):
    root = _tree(tmp_path / "app", {
        "a.ts": "import b from './b';\nimport r from 'react';\nexport class A {}\n",
        "b.ts": "export const b = 1;\n",
    })
    outs = []
    for name in ("one", "two"):
        folder = tmp_path / name
        assert main(["project-intake", str(root), "--language", "javascript", "--system", "S",
                     "--goal", "G", "--requirement", "R", "--output", str(folder)]) == 0
        outs.append({p.name: p.read_bytes() for p in folder.iterdir()})
    assert outs[0] == outs[1]


def test_no_code_is_executed(tmp_path):
    marker = tmp_path / "EXECUTED"
    root = _tree(tmp_path / "app", {
        "evil.js": f"require('fs').writeFileSync({str(marker)!r}, 'x');\nimport './other.js';\n",
        "other.js": "throw new Error('MUST NEVER RUN');\n",
    })
    folder = tmp_path / "out"
    assert main(["project-intake", str(root), "--language", "javascript", "--system", "S",
                 "--goal", "G", "--requirement", "R", "--output", str(folder)]) == 0
    assert not marker.exists()
    assert "MUST NEVER RUN" not in (folder / "intake-review.md").read_text()


def test_mts_and_cts_are_not_in_the_shared_inventory_allowlist(tmp_path):
    # .mts/.cts are outside source_evidence.SOURCE_SUFFIXES (not owned by this
    # feature); they are neither inventoried nor analysed, and the docs say so.
    root = _tree(tmp_path / "app", {"a.ts": "export {};\n", "b.mts": "export {};\n", "c.cts": "export {};\n"})
    result = _intake(root)
    assert set(_modules(result)) == {"a"}
    assert {f.path for f in result.inventory.files} == {"a.ts"}


# ------------------------------------------------------- CLI and Python path


def test_default_language_is_python_and_javascript_flag_rejects_unknown(tmp_path, capsys):
    root = _tree(tmp_path / "app", {"a.py": "x = 1\n", "b.js": "export {};\n"})
    folder = tmp_path / "py"
    assert main(["project-intake", str(root), "--system", "S", "--goal", "G",
                 "--requirement", "R", "--output", str(folder)]) == 0
    obs = IntakeObservations.model_validate_json((folder / "module-observations.json").read_text())
    assert obs.method == "python_ast_static_imports"
    assert [m.module for m in obs.modules] == ["a"]
    assert "internal_imports" in json.loads((folder / "module-observations.json").read_text())["modules"][0]
    # JS-only keys must not appear in Python output
    text = (folder / "module-observations.json").read_text()
    for key in ("external_imports", "unresolved_imports", "type_only_imports", "dynamic_imports",
                "variables", "ambiguous_slashes", "lexical_anomalies"):
        assert key not in text
    with pytest.raises(SystemExit):
        main(["project-intake", str(root), "--language", "ruby", "--system", "S", "--goal", "G",
              "--requirement", "R", "--output", str(tmp_path / "x")])
    capsys.readouterr()


def test_python_language_on_js_only_project_still_fails_with_python_message(tmp_path):
    root = _tree(tmp_path / "app", {"b.js": "export {};\n"})
    with pytest.raises(ValueError, match="No Python source modules found"):
        prepare_project_intake(root, system="S", goal="G", requirements=["R"])


def test_unknown_language_is_rejected_by_the_api(tmp_path):
    root = _tree(tmp_path / "app", {"b.js": "export {};\n"})
    with pytest.raises(ValueError, match="language"):
        prepare_project_intake(root, system="S", goal="G", requirements=["R"], language="ruby")


def test_javascript_project_with_only_python_files_fails_with_js_message(tmp_path, capsys):
    root = _tree(tmp_path / "app", {"a.py": "x = 1\n"})
    code = main(["project-intake", str(root), "--language", "javascript", "--system", "S",
                 "--goal", "G", "--requirement", "R", "--output", str(tmp_path / "o")])
    assert code == 1
    assert "No JavaScript/TypeScript source modules" in capsys.readouterr().err
    assert not (tmp_path / "o").exists()


# ----------------------------------------------------------------- pipeline


def test_full_pipeline_on_small_ts_project(tmp_path):
    root = _tree(tmp_path / "shop", {
        "src/index.ts": "import { Cart } from './cart/cart';\nimport { pay } from './payment';\n"
                        "import express from 'express';\nexport function start() {}\n",
        "src/cart/cart.ts": "import type { Item } from './item';\nimport { pay } from '../payment';\n"
                            "export class Cart {}\n",
        "src/cart/item.ts": "export interface Item { id: string }\n",
        "src/payment/index.ts": "export function pay() {}\n",
        "README.md": "docs",
    })
    intake = tmp_path / "intake"
    assert main([
        "project-intake", str(root), "--language", "javascript", "--system", "Shop",
        "--goal", "Document the current module structure",
        "--requirement", "Customers can pay for a cart", "--output", str(intake),
    ]) == 0
    arch = tmp_path / "arch"
    assert main(["design", str(intake / "brief.json"), "--fixture", str(intake / "design.json"),
                 "--output", str(arch)]) == 0
    spec = ArchitectureSpec.model_validate_json((arch / "architecture.json").read_text())
    assert spec.status == "incomplete_requires_review"
    review = tmp_path / "review"
    assert main(["review", str(arch / "architecture.json"), "--output", str(review)]) in (0, 2)
    docs = tmp_path / "docs"
    assert main([
        "document", str(arch / "architecture.json"),
        "--review", str(review / "architecture-review.json"),
        "--source-root", str(root), "--source-evidence", str(intake / "source-evidence.json"),
        "--output", str(docs),
    ]) == 0
    assessment = assess_sources(
        spec, SourceEvidence.model_validate_json((intake / "source-evidence.json").read_text()), root)
    assert all(c.status == "matching_snapshot" for c in assessment.checks)
    assert (docs / "source-evidence.md").is_file()

    # structure-diff between two intakes after a source change
    (root / "src/cart/item.ts").write_text("export interface Item { id: string }\nexport const extra = 1;\n")
    (root / "src/payment/index.ts").write_text(
        "import { Cart } from '../cart/cart';\nexport function pay() {}\n")
    second = tmp_path / "intake2"
    assert main([
        "project-intake", str(root), "--language", "javascript", "--system", "Shop",
        "--goal", "Document the current module structure",
        "--requirement", "Customers can pay for a cart", "--output", str(second),
    ]) == 0
    diff = compare_module_observations(load_module_observations(intake), load_module_observations(second))
    assert diff.structure_changed
    assert [(e.source, e.target) for e in diff.edges_added] == [("src/payment/index", "src/cart/cart")]
    sd = tmp_path / "sd"
    assert main(["structure-diff", str(intake), str(second), "--output", str(sd)]) == 0
    assert (sd / "structure-diff.md").is_file()

    impact = tmp_path / "impact"
    assert main(["source-impact", str(intake / "source-inventory.json"),
                 str(second / "source-inventory.json"),
                 "--evidence", str(intake / "source-evidence.json"),
                 "--architecture", str(arch / "architecture.json"), "--output", str(impact)]) == 0
    gate = tmp_path / "gate"
    assert main(["doc-gate", str(arch / "architecture.json"),
                 "--review", str(review / "architecture-review.json"),
                 "--source-root", str(root), "--source-evidence", str(intake / "source-evidence.json"),
                 "--output", str(gate)]) == 0
    assert any(gate.iterdir()) and any(impact.iterdir())
