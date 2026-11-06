# JavaScript / TypeScript project intake — from a source folder to architecture documentation

`speccanopy project-intake PROJECT --language javascript` performs an **offline, bounded, lexical scan** of a local JavaScript/TypeScript project and prepares the **same six artifacts, with the same schemas**, as the Python intake ([python-project-intake.md](python-project-intake.md)). Because the artifacts are identical in shape, `design`, `review`, `document`, `doc-gate`, `source-impact`, `source-diff` and `structure-diff` work on them unchanged.

**Important:** this is a **provisional technical inventory**, not an AI architect, not a JavaScript parser or type-checker, not a build-tool or bundler resolver, and not a business-requirement extractor. Every edge is a **syntax observation**: a string literal found after `import`, `export ... from`, `require(` or `import(`. **No code is executed, imported, transpiled, bundled or sent to a model; no Node.js is needed; there is no network access and no paid API.** The project owner supplies the real requirements.

## 1. Command and inputs

```bash
speccanopy project-intake ~/projects/my-web-app \
  --language javascript \
  --system "My Web App" \
  --goal "Document the architecture of the current application" \
  --requirement "Customers can pay for the items in their cart" \
  --output out/my-web-app-inputs
```

| Input | Notes |
| --- | --- |
| `PROJECT` | Local folder you are authorized to analyze |
| `--language` | `python` (default, unchanged behaviour) or `javascript` |
| `--system`, `--goal`, `--requirement` (repeatable) | Human-supplied, same rules as the Python intake |
| `--max-modules` (default 30, max 50), `--max-files` (default 2000, max 10000), `--max-file-bytes` (default 1,000,000, max 5,000,000) | Same bounds as the Python intake |
| `--output` | New or empty directory; existing non-empty output is rejected |

The default `--language python` path is byte-for-byte the previous behaviour. Then run `design`, `review` and `document` exactly as in section 3 of the Python guide, with the JavaScript intake directory.

## 2. Outputs

Identical file set to the Python intake: `brief.json`, `design.json`, `source-evidence.json`, `source-inventory.json`, `module-observations.json`, `intake-review.md`.

Differences are confined to `module-observations.json` and `intake-review.md`:

* `method` is `"javascript_lexical_imports"` (Python keeps `"python_ast_static_imports"`).
* `excluded_non_python_source` (a legacy field name) lists allowlisted source/schema files that were **not** analyzed, for example `.d.ts` files, `*.min.js`, `*.test.*` / `*.spec.*` and files of other languages.
* Each module additionally carries optional fields that the Python output omits entirely: `variables`, `variables_omitted`, `external_imports`, `unresolved_imports`, `type_only_imports`, `dynamic_imports`, `nonliteral_dynamic_references`, `ambiguous_slashes`, `lexical_anomalies`. Older readers and `structure-diff` ignore them.
* `intake-review.md` has extra sections: external packages (names only), unresolved references, **lexical caveats** (per file), plus counts for every ambiguity the lexer met.

### Modules and component IDs

* A **module** is the project-relative POSIX path **without its final extension**, for example `src/api/index` for `src/api/index.ts`. Index files keep their path; there is no `src/` stripping and no dotted names.
* One candidate component per module, with the same ID scheme as the Python intake (`mod_` + 14 hex digits of SHA-256 of the file path). Edge IDs likewise are `dep_` + hash of source and target paths.
* Two files with the same path stem (`a.js` and `a.ts`) make the module name ambiguous and the command **fails closed** with an explicit message. Select a narrower folder.

### Symbol mapping (names only, no bodies)

| Observation field | Contains (top-level, brace/paren/bracket depth 0) |
| --- | --- |
| `functions` | `function`, `async function`, `function*` declarations (also `export` / `export default` / `declare` forms) |
| `classes` | `class` and `abstract class`, plus the TypeScript named declarations `interface`, `type` aliases and `enum` / `const enum` |
| `variables` (JS/TS-only) | the **first** declarator name of each top-level `const` / `let` / `var` |

`structure-diff` compares `functions` and `classes`, so interface/type/enum changes are visible there; `variables` are not compared by it. Lists are capped at 30 names each (`symbols_omitted` / `variables_omitted` count the rest), as in the Python intake. Not recorded: later declarators in `const a = 1, b = 2`, destructured names, `namespace` / `module` blocks, anonymous default exports, anything nested in a block or function.

## 3. What the lexer recognises

The scanner is a small **hand-written lexer, not a parser and not regular expressions over raw text**. It splits the file into tokens, skipping everything that is not code:

* line comments, block comments and a leading `#!` hashbang;
* `'…'` and `"…"` strings;
* template literals, including `${ … }` expressions and nested templates (scanned iteratively with a nesting cap of 200, so hostile input cannot raise `RecursionError`);
* regex literals, decided by the previous-significant-token heuristic below.

Text inside any of these is never read as an import, so `// import a from './a'`, `` `import ${x} from './b'` `` and `const r = /import x from 'y'/;` produce **no** edge.

From the remaining tokens it recognises:

| Form | Recorded as |
| --- | --- |
| `import … from 'x'`, `import 'x'`, `import x, { y } from 'x'`, `import * as n from 'x'` (statement start, depth 0) | static reference |
| `import type … from 'x'` | static reference flagged **type-only** |
| `export * from 'x'`, `export * as n from 'x'`, `export { a } from 'x'`, `export type { A } from 'x'` | static reference (type-only when `export type`) |
| `require('x')` anywhere, including `import x = require('x')` | `require` reference |
| `import('x')` anywhere | `dynamic` reference |
| `require(expr)` / `import(expr)` whose argument is **not exactly one plain string literal** (variable, concatenation, template literal) | counted in `nonliteral_dynamic_references`; never resolved |

`import { type A } from 'x'` is treated as a normal (not type-only) reference, because with `verbatimModuleSyntax` / side-effect preservation it may still load the module. `import('./x')` inside a type position is recorded as a dynamic reference even though it can be type-only. Member access (`obj.require(...)`, `x?.import(...)`, `import.meta`), `function require(...)` declarations and methods named `require` / `import` (a call whose closing `)` is followed by `{`) are not references.

## 4. How specifiers become edges

* **Relative** specifiers (`.`, `..`, `./…`, `../…`) are resolved against the **observed file set only**. First stage with a hit wins: (1) the exact path — for `./a.js` also `a.ts` / `a.tsx` (`.jsx`→`.tsx`, `.mjs`→`.mts`, `.cjs`→`.cts`), the TypeScript convention of writing the output extension; (2) the path plus each allowed extension; (3) `/index` plus each allowed extension. A file with extension therefore wins over a same-named directory index. More than one hit in one stage would be recorded as unresolved, never guessed (in practice the unique-module-name rule fails earlier). A specifier that resolves to nothing observed — a missing file, an asset such as `./style.css`, a `.d.ts`, a path leaving the project — is listed under `unresolved_imports`. A module that imports itself produces no edge.
* **Bare** specifiers (`react`, `lodash/fp`, `@scope/pkg/sub`, `node:fs`) are **external packages**: they are **not edges**. Only the package name is listed per module in `external_imports` (`lodash/fp` → `lodash`, `@scope/pkg/sub` → `@scope/pkg`).
* **Not resolved, by design:** `tsconfig.json` / `jsconfig.json` `paths` and `baseUrl` aliases, `package.json` `exports` / `imports` / `main` / `workspaces`, bundler aliases and monorepo package links. Specifiers like `@/utils`, `~/x`, `#internal/x` or absolute paths are recorded as unresolved. A `baseUrl`-style import such as `src/utils` looks like a bare package name and is listed as an **external package named `src`** — check the external list for names of your own folders. Cross-package edges in monorepos are therefore missing.
* `edge` evidence: every edge has a `SourceClaim` with basis `observed` at the first line of the earliest reference, bound to the source file's SHA-256 exactly like the Python intake. The edge description lists the reference forms seen (static, type-only, `require()`, dynamic `import()`).

## 5. Exact limits and heuristics

1. **Regex versus division.** A `/` that is not a comment is read as the start of a regex literal when the previous significant token is: nothing, a punctuator other than `)`, `]`, `}`, `++`, `--`, `<`, or one of the keywords `return typeof instanceof in of new delete void throw case do else yield await` (not when the keyword is a property name after `.`). In every other case it is division. Wrong in both directions are possible, for example `if (x) /re/.test(y)` and a statement that starts with a regex right after `}`. These two undecidable cases (`/` after `)` or `}`) are **counted** (`ambiguous_slashes`, surfaced per file in `intake-review.md`) and treated as division. A regex that does not close before a line break is not a regex: the `/` is treated as punctuation and a lexer recovery is counted. A regex literal containing a quote, backtick or brace *inside a template `${ }` expression* can desynchronise that template scan.
2. **Recoveries.** An unterminated string ends at the line break (so JSX text such as `Don't` costs one counted recovery, not a failure), an unterminated block comment or template ends at end of file, extra closing brackets and over-deep template nesting are counted. `lexical_anomalies` and the review list the affected files; a non-zero count means the file deserves a manual look. Invalid UTF-8 fails the whole intake, like a Python syntax error.
3. **No JSX semantics.** JSX is not parsed. `</tag>` is guarded against being read as a regex, but brace depth and declaration detection can be skewed in JSX-heavy files, and text such as `http://x` inside JSX text can be lexed as a comment. Only module-level imports and declarations are used, so edges are rarely affected, but declarations may be missed.
4. **No framework conventions.** Next.js / Remix file routing, Angular decorators and modules, NestJS providers, dependency injection, `jest.mock`, `require.resolve`, `import.meta.glob`, dynamic `import(variable)`, webpack magic comments, Vue / Svelte single-file components and runtime plugin loading are not interpreted. Static imports can be conditional, type-only or dead code.
5. **Declarations** are detected only at depth 0 at a statement start (after `;`, `}`, a line break, or modifier keywords such as `export default async`). Automatic-semicolon-insertion cases are handled by the line-break rule, not by a real grammar.
6. **Files analyzed:** `.js .jsx .mjs .cjs .ts .tsx` in the shared source allowlist. **Excluded from analysis** (listed as not analyzed): `.d.ts` declaration files, minified `*.min.*`, `*.test.*` and `*.spec.*` files, and files the inventory classifies as tests (`tests/`, `__tests__/`, `test_*`). Also never read, by the shared privacy filters: dot-directories and dot-files (such as `.env`), `node_modules`, `dist`, `build`, `out`, `coverage`, `vendor`, symlinks, directories named `private`, `secrets` or `credentials`, and path segments containing words such as `secret`, `credential`, `password`, `token`. `.mts` / `.cts` files are **not** in the shared inventory allowlist today, so they are neither inventoried nor analyzed; extending that allowlist is a separate, deliberate change because it changes the recorded inventory policy.
7. **Bounds** are the Python intake's: module count, file count, per-file byte size (oversized files are counted in `skipped_oversized_files`, never silently read). Scan time grows linearly with file size, on the order of seconds per MB of code.
8. **Nothing is executed.** Files are only read as bytes, hashed and tokenised; a file containing `require('fs').writeFileSync(...)` or `throw` is just text. The tests prove this with marker files.

## 6. After intake

Use the generated draft exactly like the Python one: run `design`, `review` and `document` (with `--source-root` and `--source-evidence`) and keep their `incomplete_requires_review` status until a human maps real requirements to components. Re-run intake into a new empty directory after source changes and compare with `speccanopy structure-diff old new`, `source-diff` and `source-impact`. Open `intake-review.md` first and read **Unresolved references**, **External packages** and **Lexical caveats** before trusting the graph. This milestone does not complete [Issue #5](https://github.com/MSKazemi/speccanopy/issues/5): semantic extraction, monorepo/alias resolution and evaluation on a rights-cleared real application remain open.

Filenames, symbol names and package names in the output may be confidential; review before publishing generated files.
