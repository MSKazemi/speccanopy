# Pilot: Speccanopy on a real third-party Python package

**Run 2026-11-06 by the maintainers' tooling. Not an owner-confirmed evaluation and not independent expert review.** The package's maintainers were not involved, did not confirm any observed fact, and did not supply requirements. This pilot measures what Speccanopy's deterministic pipeline does on real, unmodified source code. It does not show that the generated architecture is correct.

## Subject

| Item | Value |
| --- | --- |
| Package | [itsdangerous](https://github.com/pallets/itsdangerous) by Pallets |
| License | BSD-3-Clause (`LICENSE.txt` in the wheel); no source is copied into this repository |
| Versions | 2.2.0 (main run) and 2.1.2 (release-change run) |
| Input | Official PyPI wheels, unpacked without building or executing anything |
| Wheel SHA-256 | 2.2.0: `c6242fc49e35958c8b15141343aa660db5fc54d4f13a1db01a3f5891b98700ef`<br>2.1.2: `2c2349112351b88699d8d4b6b075022c0808887cb7ad10069318a8b0bc88db44` |

Why this package: small (8 modules), pure Python, no runtime dependencies, permissive license, and a real public release history to diff.

## Reproduce

Work in a scratch directory and keep each download in its own empty folder. Downloading a **wheel** (`--only-binary :all:`) avoids running any build backend.

```bash
python -m pip download --no-deps --only-binary :all: itsdangerous==2.2.0 -d dl-220
python -I -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" dl-220/itsdangerous-2.2.0-py3-none-any.whl app

speccanopy project-intake app --system "itsdangerous 2.2.0 (third-party pilot)" \
  --goal "PILOT: document module boundaries of a small real-world signing library" \
  --requirement "Sign data so that a token passed to an untrusted environment can be checked for tampering when it comes back (from the project README)" \
  --requirement "Allow customizing how signed data is serialized, compressing it as needed (from the project README)" \
  --requirement "Optionally add a timestamp to a token and verify its age while loading (from the project README)" \
  --output work/intake
speccanopy design work/intake/brief.json --fixture work/intake/design.json --output work/design
speccanopy review work/design/architecture.json --output work/review
speccanopy doc-gate work/design/architecture.json --review work/review/architecture-review.json \
  --source-root app --source-evidence work/intake/source-evidence.json --output work/doc-gate
speccanopy document work/design/architecture.json --review work/review/architecture-review.json \
  --source-root app --source-evidence work/intake/source-evidence.json --output work/docs
```

The three requirements are **paraphrased from the project's README by the pilot operator**. They are not owner-supplied.

## Results — 2.2.0

| Stage | Observed |
| --- | --- |
| `project-intake` | exit 0; `8 modules, 21 static import edges`; no code executed |
| `design` | exit 0; 9 components (root + 8 modules), depth 1; mandatory requirements `0 verified, 0 planned, 3 uncovered` |
| `review` | exit 0; `requires_review`; style recommendation: abstain; 3 quality findings |
| `doc-gate` | exit 0; `requires_review (20 blocking, 12 attention)` |
| `document` | exit 0; `29/29 byte snapshots match`; status stays `incomplete_requires_review` |

**Intake accuracy against an independent check.** The pilot operator listed every `from .x import` statement in the package with a regular expression, separately from Speccanopy's AST code. Result: **21 of 21** internal module edges found, **0** extra, **8 of 8** modules. This checks only static import syntax. It does not check runtime behaviour, which the intake does not claim to observe.

**What the gate blocked on.**

| Category | Blocking | Attention |
| --- | --- | --- |
| Uncovered requirements | 3 | 0 |
| Unknown source mappings | 4 | 0 |
| Remaining manual decisions | 13 | 12 |

These are the expected gaps: no component is mapped to the three requirements, modules are provisional `requires_review` components, and the review's high findings repeat the coverage gap. A human has to map requirements to modules (for example, timestamp verification to `itsdangerous.timed`) before the pack is useful.

**Usability problem found and fixed.** Gate messages named components only by intake IDs such as `mod_158538b88c3e3c`, which a reader cannot map to a module. Messages now show `mod_… (Python module itsdangerous.signer)`.

## Results — real release change 2.1.2 → 2.2.0

Evidence was authored by `project-intake` on 2.1.2. Then:

```bash
speccanopy source-inventory app-220 --output inv-220.json
speccanopy source-diff intake-212/source-inventory.json inv-220.json --output diff
speccanopy source-impact intake-212/source-inventory.json inv-220.json \
  --evidence intake-212/source-evidence.json --architecture design-212/architecture.json --output impact
```

| Observation | Value |
| --- | --- |
| `source-diff` | `0 added, 1 removed, 8 changed, 0 unchanged`; no rename candidates |
| Removed path | `itsdangerous-2.1.2.dist-info/LICENSE.rst` (2.2.0 ships `LICENSE.txt`, which is not on the inventory allowlist) |
| `source-impact` | `29 claims (29 stale_changed)`, all 29 IDs possibly affected; exit 0 |
| Static import structure | 21 edges in both versions, **identical set** |
| `structure-diff` | modules `0 added, 0 removed, 8 kept`; edges `0 added, 0 removed, 21 kept`; **3** kept modules gained top-level symbols; **5** of 8 byte-changed modules are structurally unchanged; `Structure changed: yes` (exit 2 with `--strict`) |

All eight modules changed bytes in this release (for example `typing` modernisation in `signer.py`), so every digest-bound claim is correctly reported as stale. The module-import graph did not change. **Digest-level impact therefore flags every claim, including the 21 import-edge claims whose edges are still present.** It never misses a changed cited file, but on whole-release diffs many flags are false alarms for structural claims.

`speccanopy structure-diff` separates the two. Run `project-intake` on each version, then:

```bash
speccanopy structure-diff intake-212 intake-220 --output structure
```

It reports three kept modules with new top-level symbols: `__getattr__` in `itsdangerous`, class `_PDataSerializer` in `itsdangerous.serializer`, and `_lazy_sha1` in `itsdangerous.signer`. Each was confirmed absent in 2.1.2 and present in 2.2.0 by a separate `grep`. The other five modules changed bytes only. An earlier draft of this report said the structure was unchanged; that was true of the import graph only. See [Structural comparison](structure-diff.md).

`--architecture` must be the generated `architecture.json`. Passing `brief.json` fails cleanly with exit 1.

## Limits

- One small library. Results do not generalise to larger, multi-language or service-based systems.
- No owner confirmed any fact, requirement or module role; the requirements are a paraphrase of public README text.
- Intake accuracy was checked only for static import edges, against a regex count by the same operator, not a labelled corpus.
- Nothing here is expert validation, and the architecture status was never promoted.

## JavaScript pilot — commander 12.1.0

Same method, with `project-intake --language javascript`, on [commander](https://github.com/tj/commander.js) 12.1.0 (MIT), from the official npm tarball (SHA-256 `56affc6ddafe486f94b428ae2823d059cf60d4dae2f33eaaf1b1ec4306f73173`), extracted with Python's `tarfile` `data` filter; nothing installed or executed. Requirements were paraphrased from the README by the pilot operator.

```bash
speccanopy project-intake package --language javascript --system "commander 12.1.0 (third-party pilot)" \
  --goal "PILOT: document module boundaries of a real CLI-parsing library" \
  --requirement "Parse command-line options and arguments into a program's configuration (from the project README)" \
  --requirement "Generate help text for commands and options (from the project README)" \
  --output work/intake
```

| Check | Observed |
| --- | --- |
| Modules | 8 of 8 (`esm`, `index`, `lib/argument`, `lib/command`, `lib/error`, `lib/help`, `lib/option`, `lib/suggestSimilar`); `typings/index.d.ts` listed as not analysed |
| Internal import edges vs. a separate `grep` of every `require(`/`import` line | **14 of 14**, 0 extra, including the extension-less `require('./suggestSimilar')` |
| External imports | exactly the five `node:` built-ins in `lib/command.js`, none treated as edges |
| JSDoc text such as `require.main.filename` | not counted |
| Top-level classes and functions | match a `grep` of `^class `/`^function ` in every module |
| Lexer diagnostics | 1 ambiguous `/` in `lib/suggestSimilar.js` (reported, not guessed); 0 lexical anomalies |
| Rest of pipeline | `design`, `review`, `document` exit 0; `22/22` byte snapshots match; `doc-gate` `requires_review (18 blocking, 12 attention)` |

`typings/esm.d.mts` does not appear at all: `.mts`/`.cts` are not on the shared inventory allowlist yet. As with the Python pilot, this checks static import syntax on one small CommonJS library; it says nothing about behaviour, larger TypeScript code bases with path aliases, or JSX-heavy front ends.
