# PlanX DataCube Lab — Enhancement Plan v1.3.0 ("Toolbox-Linked, pytest-Native, Regression-Guarded")

**Audience:** an external implementation agent (DeepSeek). Work through the phases IN ORDER.
**Repository:** `planx_datacube/` inside the `qgis_plugins` monorepo.
**Current version:** 1.2.1 → **Target version:** 1.3.0 (single release at the end).
**Baseline facts (verified 2026-07-10):** 8 Processing algorithms in one group (`Spatiotemporal Analysis` / groupId `spatiotemporal_analysis`), `ui/datacube_dashboard.py` = 965 lines, `tests/test_core.py` = ~95 pure-logic checks (custom script harness, not pytest-discoverable, ~440 lines), real-QGIS e2e at `scratch/datacube_e2e_qgis.py` (440 lines, exercises all 8 algorithms, no algorithm-count pin), `bandit` = 5 Low findings / 0 Medium+, `flake8` = 62 findings (mostly F401 unused imports), zero Turkish-language debt (this plugin is already English-only and already has `shortHelpString()` on all 8 algorithms — ahead of its siblings there).

---

## 0. Non-negotiable ground rules (read before touching anything)

1. **Read the monorepo docs first:** `qgis_plugins/AGENTS.md` and `qgis_plugins/RELEASING.md`. Their conventions (LICENSE present, `experimental=False`, centralized `packaging/release.ps1`) are mandatory. This plugin already satisfies LICENSE/`experimental=False` — do not regress them.
2. **No literal `%` in `metadata.txt`** — a bare `%` breaks the QGIS Hub upload (configparser interpolation). Currently clean — keep it that way; `grep -n "%" metadata.txt` must return nothing at the end.
3. **No self-praise wording** anywhere in user-facing copy: never write "elite", "best", "ultimate", "world-class". `metadata.txt` line 10 currently uses "revolutionises" — reword it to a factual claim (e.g., "brings space-time cube analytics to QGIS") while you're touching that file for the version bump in Phase 6; this is a minor wording fix, not a hard blocker for earlier phases.
4. **No AI attribution:** never add `Co-Authored-By: Claude` (or DeepSeek, or any AI) trailers to commits.
5. **Never weaken an existing test or gate.** `tests/test_core.py` currently reports ~95/95 checks and `scratch/datacube_e2e_qgis.py` exercises all 8 algorithms with passing numeric assertions (hot/cold cluster recovery, HH/LL LISA, MK trend sign/slope, anomaly detection, backtest RMSE, netCDF export) — these counts/assertions may only go UP or stay equally strict. If a check blocks you, fix the code, not the check. Any genuinely necessary change to an expectation must be justified in the report (Section R).
6. **Security scan:** the QGIS Hub runs Bandit/detect-secrets/Flake8 and hard-blocks Critical findings (especially SHA-1/MD5, B303/B324). Current baseline is 5 Low-only findings — the count of Low findings must not increase without justification, and no Medium/High/Critical may be introduced.
7. **This plugin has no Turkish-language debt and no bilingual UI machinery.** Do not add any — keep it English-only as it already is.
8. **New algorithm/behavior registration rule:** anything you add or rename must stay consistent across `processing/datacube_provider.py`, the README's tool list, and (if you create one — see Phase 4) a command-guide doc.
9. **Do not bump the version or write the changelog until Phase 6.** Do not release/tag/upload — the maintainer releases manually after review.
10. Work on the current branch (`master`); make small, well-scoped commits per phase with messages like `phase-1: add helpUrl to all 8 algorithms`.

---

## Phase 1 — `helpUrl()` for all 8 algorithms (the one real toolbox-documentation gap)

**Finding:** all 8 algorithms already implement `shortHelpString()` with specific, non-boilerplate text (e.g. `alg_run_ehsa.py:111-124`) — this plugin is ahead of its siblings there. But **zero** implement `helpUrl()`, so the Processing dialog's help-icon link does nothing for any DataCube algorithm.

### 1.1 Add `helpUrl()` to all 8 algorithm classes
Files under `processing/`: `alg_create_cube.py`, `alg_space_time_cube.py`, `alg_run_ehsa.py`, `alg_local_morans.py`, `alg_temporal_trend.py`, `alg_temporal_anomaly.py`, `alg_forecast_backtest.py`, `alg_forecast.py`.

- Add a shared mixin (e.g. `processing/_help_mixin.py`) or per-class `helpUrl()` returning `https://github.com/YusufEminoglu/planx_datacube` (repo root, or a per-algorithm anchor into the README's tool list if practical). Must not change any algorithm's `name()`, `displayName()`, `group()`, `groupId()`, or parameter definitions.

### 1.2 Regression guard: pin the algorithm count in e2e
- In `scratch/datacube_e2e_qgis.py`, right after provider registration, add: `assert len(list(provider.algorithms())) == 8, f"expected 8 algorithms, got {len(list(provider.algorithms()))}"`. This closes the one regression gap the e2e harness currently has (all 8 algorithms are already exercised — this phase only adds the missing count assertion, it does not need to add new algorithm coverage).
- Re-run the full e2e on both QGIS 3.44 (`python-qgis-ltr.bat`) and QGIS 4.x (`python-qgis.bat`) and paste the complete console output in the report.

**Phase 1 exit criteria:** `grep -rln "def helpUrl" processing | wc -l` returns 8; e2e script contains the `== 8` assertion; both QGIS 3.44 and 4.x e2e runs pass with full output pasted in the report.

---

## Phase 2 — Surface the silent forecasting fallback (real UX gap)

**Finding:** `core/forecasting_studio.py` silently falls back from ARIMA to exponential smoothing when `statsmodels` is unavailable (lines ~55-79: `except ImportError: return exponential_smoothing(...), "exponential_smoothing"`), and similarly for the Random Forest path (lines ~102-106) when `sklearn` is unavailable. The chosen method IS written to the `forecast_method` output field by `alg_forecast.py:118`, so it's discoverable in the output attribute table — but nothing tells the user *while running* that their requested method silently changed.

- In `alg_forecast.py` (and `alg_forecast_backtest.py` if it shares the same forecasting core), after calling into `forecasting_studio`, compare the requested method against the returned method string; if they differ, call `feedback.pushWarning(...)` (or `pushInfo` if `pushWarning` isn't available on the feedback object used here — check the QGIS API in use) with a clear one-line message, e.g. "statsmodels not available — used Exponential Smoothing instead of ARIMA". Do not change the underlying fallback behavior or its return value, only add the visible warning.
- Verify this doesn't fire when the requested and actual methods match (i.e., no spurious warning on the normal path).

**Phase 2 exit criteria:** running the Forecasting Studio / Forecast Backtest algorithm on an environment lacking `statsmodels`/`sklearn` (the OSGeo4W environment already lacks them per project convention) shows the warning in the Processing log; e2e or unit test confirms the warning path is reachable (e.g., assert on `feedback.warnings` list if the test feedback stub tracks it, or add such tracking to the stub if it doesn't).

---

## Phase 3 — Lint cleanup (scoped, not a blanket sweep)

**Finding:** `flake8 --max-line-length=140 --extend-ignore=E203,W503` reports 62 findings, mostly F401 unused imports concentrated in a few files.

- Remove unused imports: `core/cube_builder.py` (9 F401), `processing/alg_create_cube.py` (4 F401), `ui/datacube_dashboard.py` (`QUrl` line ~17, `QDesktopServices` line ~18, `check_packages` line ~663), `ui/voxel_config_dialog.py` (`QSpinBox`), `layout/timeslice_stacker.py` (`QColor`), `core/dependency_manager.py`.
- Fix F841 unused locals: `core/cube_builder.py:259` (`prov`), `core/statistics_ehsa.py:171` (`unique`) — confirm each is genuinely dead (not a debugging leftover that should instead be used) before deleting.
- Fix F541 f-strings missing placeholders: `core/dependency_manager.py:120,126` (convert to plain strings, they don't need f-prefix).
- Fix the E127/E128 continuation-indent issues in `alg_create_cube.py` (6×) and `datacube_dashboard.py` (2×) since you're already touching these files.
- Do NOT restructure or reformat `tests/test_core.py` in this phase — its ~30 E302/E305/E402/E221/E701/F824-style findings are addressed in Phase 4 (pytest conversion), not here, to avoid two unrelated diffs touching the same file.
- The 2 bandit B110 (`processing/symbology.py:67-68`, `:88-89`, try/except/pass around best-effort symbology) should log via `feedback.pushInfo` instead of silently passing, same pattern as sibling plugins' hardening — but only if `feedback` is in scope at that call site; if it isn't, leave as-is and note why in the report.
- `core/local_morans.py:91`'s `random.Random(seed)` (bandit B311) is a false positive — it's deterministic permutation testing, not security-sensitive. Add a `# nosec B311` comment with a one-line reason instead of changing the RNG.

**Phase 3 exit criteria:** flake8 findings drop from 62 to a number you report exactly (excluding `tests/test_core.py`'s pre-existing script-style findings, which Phase 4 addresses); zero F401 in the files listed above; bandit still shows 0 Medium/High/Critical and the Low count does not increase (the `# nosec` on `local_morans.py:91` should reduce it by one).

---

## Phase 4 — Convert `tests/test_core.py` to pytest-discoverable form

**Finding:** `tests/test_core.py` is a single script that runs everything at import time via a custom `check()`/`section()` harness and calls `sys.exit()` — it is NOT discoverable by `python -m pytest tests/` (diverges from sibling plugins' `pytest -q` gate). It currently passes ~95 checks when run directly with plain `python`.

- Refactor into proper `def test_*()` functions grouped by the existing 14 sections (EHSA Gi*, Mann-Kendall, 17-class classification, ES/ARIMA/RF forecasting, cube builder, dependency manager, spatial weights, Local Moran's I, timeseries stats, backtest, etc.), using plain `assert` statements instead of the custom `check()` calls. Preserve every existing assertion's condition exactly — this is a mechanical conversion, not a chance to loosen or drop checks.
- Keep this qgis-free (mocks `qgis.*` as it currently does) so it stays fast and runnable with plain `python -m pytest`.
- After conversion, `python -m pytest tests/test_core.py -q` must report at least the same number of passing assertions as the current ~95 checks (pytest will report test-function count, not raw assertion count — make sure no assertion was silently dropped by grepping the old file's `check(` call count vs. the new file's `assert` count as a sanity cross-check, and report both numbers).
- Run the Phase-3-deferred flake8 cleanup on this file now that it's pytest-shaped (E302/E305/E402/E221/E701/F824 should mostly disappear naturally from the restructuring; fix what remains).

**Phase 4 exit criteria:** `python -m pytest tests/test_core.py -q` runs and passes with no collection errors; assertion-count cross-check reported in Section R; flake8 on this file shows a reported before/after count.

---

## Phase 5 — Optional parity item: command-guide doc + CITATION.cff correctness check

Both sub-items are OPTIONAL and lower priority than Phases 1–4. If you skip either, say so explicitly in the report (mark SKIPPED, not DONE) — do not silently omit them.

### 5.1 Command guide
- Sibling plugins (`planx_suitability_lab`, `planx_urban_resilience`) ship a `docs/COMMAND_GUIDE.html`. DataCube has no `docs/` directory at all. Since all 8 algorithms already have good `shortHelpString()` text, a `docs/COMMAND_GUIDE.html` listing all 8 with that same text (plus the new `helpUrl()` links from Phase 1) would bring toolbox-parity documentation in line with siblings.

### 5.2 CITATION.cff correctness
- `CITATION.cff` was added in 1.2.1. Confirm its `version:` field and author name match `metadata.txt`'s current version/author, and update it as part of the Phase 6 version bump if it needs to track the version number.

**Phase 5 exit criteria:** either the doc exists (5.1) or is explicitly marked SKIPPED with a reason; `CITATION.cff` is confirmed consistent with `metadata.txt` (fix if not).

---

## Phase 6 — Version bump & final gate (do this only when Phases 1–5 are green or explicitly SKIPPED)

1. Bump `metadata.txt` version to `1.3.0`; reword the "revolutionises" wording per rule 3 while here; add the changelog entry there too (English, no `%`, no superlatives).
2. Add the `1.3.0` section to `CHANGELOG.md` (this plugin's changelog is already clean — keep it that way, no duplicate headers). Cover: `helpUrl()` for all 8 algorithms, e2e algorithm-count regression guard, forecasting-fallback warning surfaced to the user, `tests/test_core.py` converted to pytest, lint cleanup, (Phase 5 outcomes if applicable).
3. Run the FULL gate and paste all outputs in the report:
   - `python -m pytest tests/test_core.py -q` — verify it passes and report the assertion-count cross-check from Phase 4
   - e2e script on QGIS 3.44 (`python-qgis-ltr.bat`) — full output, with the `== 8` assertion visibly passing
   - e2e script on QGIS 4.x (`python-qgis.bat`) — full output, same assertion
   - `bandit -r . -x tests,__pycache__` — must show no Medium/High/Critical; report the exact Low count vs. the baseline of 5
   - `python -m flake8 --max-line-length=140 --extend-ignore=E203,W503 .` — report exact count vs. the baseline of 62
   - `grep -n "%" metadata.txt` — empty
4. Commit; **do not tag, do not run `packaging/release.ps1`, do not upload** — the maintainer does the final release after reviewing your report.

---

## Known shortcomings register (fix or explicitly defer with reason)

| # | Shortcoming | Severity | Phase |
|---|---|---|---|
| S1 | 8/8 algorithms lack `helpUrl()` (Processing dialog help-icon link does nothing) | Medium | 1.1 |
| S2 | e2e harness has no algorithm-count pin — silent regression risk on future provider edits | Medium | 1.2 |
| S3 | ARIMA→ExponentialSmoothing and RandomForest fallback are silent to the user at run time (only discoverable via an output field afterward) | Medium | 2 |
| S4 | `tests/test_core.py` is not pytest-discoverable, diverging from sibling plugins' `pytest -q` gate convention | Medium | 4 |
| S5 | 62 flake8 findings, mostly F401 unused imports concentrated in a few files | Low | 3 |
| S6 | 2 bandit B110 try/except/pass in `processing/symbology.py` swallow best-effort styling failures silently | Low | 3 |
| S7 | `metadata.txt` uses "revolutionises" — borderline marketing wording | Low | 6 |
| S8 | No `docs/COMMAND_GUIDE.html`-style toolbox reference, unlike sibling plugins (mitigated by already-good in-toolbox `shortHelpString()`) | Low | 5.1 (optional) |
| S9 | `CITATION.cff` version/author consistency with `metadata.txt` not yet verified | Low | 5.2 (optional) |

---

## R. Required response format (your report back to the reviewer)

Deliver a single file `REPORT_v1.3.md` in the plugin root, structured EXACTLY like this — the reviewer will machine-check parts of it:

```markdown
# Implementation Report v1.3.0
## 1. Phase status
Phase 1: DONE|PARTIAL — <one line>
... (all 6 phases; Phase 5 may be SKIPPED with reason)
## 2. Shortcomings register outcomes
S1: FIXED|DEFERRED — <evidence: file/grep/test>
... (S1–S9, plus any NEW shortcomings you discovered, numbered S10+)
## 3. Algorithm helpUrl table
| algorithm id | shortHelpString (already present) | helpUrl (new) |
(8 rows, one per algorithm)
## 4. Test evidence
### 4.1 pytest output (verbatim, complete) — must show the assertion-count cross-check
### 4.2 e2e QGIS 3.44 output (verbatim, complete) — must show the `== 8` assertion passing
### 4.3 e2e QGIS 4.x output (verbatim, complete) — same
### 4.4 Forecasting-fallback warning evidence (Phase 2) — how you verified the warning fires
## 5. Gate outputs
bandit / flake8 (before vs. after counts) / metadata % grep (verbatim)
## 6. Changed-test justifications
(empty if none; otherwise every check whose expectation or form changed, old vs new, why)
## 7. Deviations from this plan
(every place you did something differently and why)
## 8. Commit list
(hash + message, one per line)
```

**Honesty over completeness:** a PARTIAL with truthful evidence is acceptable; a DONE that the reviewer's re-run contradicts invalidates the delivery.
