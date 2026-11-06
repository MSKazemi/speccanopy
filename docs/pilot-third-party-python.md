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

All eight modules changed bytes in this release (for example `typing` modernisation in `signer.py`), so every digest-bound claim is correctly reported as stale. The module-import structure did not change. **Digest-level impact therefore flags every claim even though the structure is unchanged.** It never misses a changed cited file, but on whole-release diffs most flags are likely false alarms for structural claims. Re-running `project-intake` on the new version and comparing `module-observations.json` gives a structural comparison; Speccanopy does not automate that comparison yet.

`--architecture` must be the generated `architecture.json`. Passing `brief.json` fails cleanly with exit 1.

## Limits

- One small library. Results do not generalise to larger, multi-language or service-based systems.
- No owner confirmed any fact, requirement or module role; the requirements are a paraphrase of public README text.
- Intake accuracy was checked only for static import edges, against a regex count by the same operator, not a labelled corpus.
- Nothing here is expert validation, and the architecture status was never promoted.
