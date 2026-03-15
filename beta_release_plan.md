# Beta Release Plan

> Goal: release a polished, credible beta of the LLM-based ABM to the public.
> No new features unless strictly necessary. Fix what exists; harden it.

---

## 0. Baseline Snapshot (before any changes)

Run the full pipeline with the current default prompts and store the results
as the **vanilla baseline**. All later prompt experiments compare against this.

**Steps:**

1. Run the full Snakemake pipeline end-to-end with `simulation.model: gpt-4o-mini`
   and `n_households: 200` (the current defaults in `workflow/config.yaml`).
2. Copy the output parquets (`*_trips.parquet`, `*_day_plans.parquet`,
   `*_activities.parquet`, `*_assigned_trips.parquet`) into a timestamped
   directory, e.g. `data/baselines/vanilla_YYYYMMDD/`.
3. Run `webapp/prepare_data.py` on the vanilla results and keep a copy of the
   JSON output alongside the parquets.
4. Document key aggregate statistics (trip count, mode share, average trip
   distance, average activities per agent, % of invalid day plans from
   `DayPlan.validate()`) in a short `data/baselines/vanilla_YYYYMMDD/stats.md`.

This gives a reproducible reference point. Later prompt tuning results go in
sibling directories under `data/baselines/`.

---

## 1. Fix Broken Tests and Tooling

The test suite has collection errors and mypy reports 11 errors. A beta cannot
ship with a red CI.

### 1a. Fix test collection errors

Four test files fail to collect:

| File | Cause |
|------|-------|
| `tests/test_simulate_helpers.py` | `import pandas` — pandas is a pipeline dep, not a core dep |
| `tests/workflow/test_clean_grid.py` | Same — pipeline dependency missing |
| `tests/workflow/test_sample_households.py` | Same |
| `tests/workflow/test_simulate.py` | Same |

**Action:** Add a `pytest.importorskip("pandas")` at the top of each file (or
mark them with `@pytest.mark.skipif`) so the core test suite stays green
without pipeline deps. Alternatively, move these tests into a separate pytest
marker group (e.g. `@pytest.mark.pipeline`) and skip by default.

### 1b. Fix mypy errors (11 errors in 4 files)

| File:line | Error | Fix |
|-----------|-------|-----|
| `agent.py:926` | Return type `float \| None` vs `SupportsDunderLT` | Narrow the return type or add a proper key function |
| `agent.py:1002` | Missing type params for `dict` | Add `dict[str, ...]` |
| `agent.py:1083` | Missing type params for `list` | Add `list[float]` |
| `household.py:439` | Missing type params for `list` | Add `list[...]` |
| `household.py:611` | Stale `type: ignore` + actual `attr-defined` error | Fix the POI attribute access properly (see 2d) |
| `skim.py` | Missing stubs for `openmatrix`, `numpy` | Already noted; add `# type: ignore[import-untyped]` |

**Action:** Fix all 11 errors. Zero mypy errors on `src/`.

### 1c. Fix line-length violations

`CLAUDE.md` specifies max 88 characters. Run `ruff format` and verify no
remaining violations (ruff currently passes, but double-check after edits).

---

## 2. Harden LLM Response Handling

Every LLM call returns free-form JSON. A single malformed response currently
crashes the whole household simulation. This is the single biggest reliability
risk for a public release.

### 2a. Wrap `json.loads()` in every LLM-consuming method

Methods that call `json.loads()` on raw LLM text and need try/except:

- `Agent.generate_persona()`
- `Agent.choose_work_zone()` / `choose_school_zone()`
- `Agent.generate_activities()`
- `Agent.choose_destination()`
- `Agent.schedule_activities()`
- `Agent.plan_discretionary_activities()`
- `Agent.choose_tour_mode()` (via `choose_mode()`)
- `Household.allocate_vehicles()`
- `Household.plan_escort_trips()`
- `Household.plan_joint_activities()`

**Action:** In each method, wrap `json.loads(text)` in a try/except that
catches `json.JSONDecodeError` and raises a clear `ValueError` with the step
name, agent/household id, and a truncated copy of the raw response. This lets
the caller in `simulate.py` log and skip the household gracefully (which it
already does via its try/except in `_simulate_household`).

### 2b. Validate parsed LLM data before use

After parsing JSON, add lightweight validation for known failure modes:

- **Time values:** Reject `start_time` / `end_time` outside `[0, 1440]`.
- **Mode choice:** Check that the returned mode is in the provided options
  list; if not, fall back to the cheapest-travel-time option with a warning.
- **Activity types:** Check returned types are in `VALID_OUT_OF_HOME_TYPES`;
  normalize unknown types via `normalize_activity_type()` (already exists).
- **Vehicle allocation:** Log a warning (not crash) when the LLM returns an
  `agent_id` or `tour_idx` not present in the household. The current silent
  skip is fine for robustness, but add a `logger.warning()`.
- **Zone/POI IDs:** Check that destination IDs returned by the LLM exist in
  the candidate set passed to the prompt. Log and fall back to the first
  candidate if not.

### 2c. Replace asserts with proper exceptions

Two places use `assert` for runtime validation that should be `ValueError`:

- `agent.py` `build_tours()` line ~1140: `assert act.end_time is not None`
- `day_plan.py` `validate()` lines 201-202: `assert cur.end_time is not None`

**Action:** Replace with `if ... is None: raise ValueError(...)`.

### 2d. Fix unsafe attribute access in `household.py`

`plan_joint_activities()` line ~611 does `p.id` on a POI looked up from a dict
with a stale `type: ignore`. Fix by narrowing the type properly:

```python
poi = poi_lookup.get(chosen_id)
if poi is not None:
    poi_id = poi.id
    zone_id = poi.zone_id
```

---

## 3. Strengthen Time Handling

Time parsing is fragile. LLMs return creative time formats. A robust parser
prevents silent corruption of schedules.

### 3a. Harden `_parse_hhmm()`

Current implementation splits on `:` and `T` but does no bounds checking.

**Action:** After parsing, validate:
- Hours in `[0, 23]` (or allow 24:00 as end-of-day = 1440)
- Minutes in `[0, 59]`
- Total result in `[0, 1440]`
- Raise `ValueError` with the original string on failure

Add tests for: `"24:00"`, `"25:30"`, `"08:60"`, `"abc"`, `""`, `"8:5"`.

### 3b. Clamp negative departure times in `build_tours()`

When travel time to the first activity exceeds the activity's start time,
`departure_time` goes negative. This is physically meaningless.

**Action:** Clamp departure times to `max(0.0, computed_value)` and log a
warning. Add a test for this edge case.

### 3c. Validate escort activity times

`plan_escort_trips()` computes `start_time = escort_time - 15`. If the child's
activity starts before 00:15, this goes negative.

**Action:** Clamp to `max(0.0, escort_time - offset)`. Add a test.

---

## 4. Add Missing Tests

Target: every public method in the `aibm` package has at least one happy-path
and one edge-case test. Focus on gaps that affect correctness.

### 4a. `build_tours()` — currently only tested via integration

Add direct unit tests:

- Single activity → one tour with two trips (home→act, act→home)
- Two activities at different locations → correct trip chain
- Activity at home zone → no trip generated (or zero-distance trip)
- Activity with `start_time=0` (midnight) — verify `(start_time or 0)` works
- Negative departure time (travel time > start time) — verify clamping (after 3b)

### 4b. `DayPlan.validate()` — add edge case tests

- Activities with `start_time > end_time` (backwards)
- Activities crossing midnight (end_time > 1440 after fix)
- Zero-duration work activity (start == end)
- Overlapping activities with identical times

### 4c. `_simulate_household()` — add integration test

Add one integration test (with mocked LLM) that exercises the full household
flow: persona → activities → schedule → discretionary → joint → escort →
vehicles → mode choice. Verify that the output trips dataframe has the
expected columns and no None modes.

### 4d. Retired/unemployed agent path

Add a test for an agent with `employment="retired"` — should have no work or
school activity, only discretionary. Verify `choose_work_zone` is skipped.

### 4e. Student agent path

Add a test for `employment="student"` — should call `choose_school_zone`, not
`choose_work_zone`. Currently untested in `test_simulate.py`.

---

## 5. Improve `DayPlan.validate()`

The validator exists but is underused and incomplete. For a beta release,
validation should run automatically and catch the issues ABM experts will
look for.

### 5a. Add validation checks

- **Start before end:** Warn if any activity has `start_time >= end_time`.
- **School duration:** 4-8 hours, analogous to the existing work check.
- **First departure / last arrival:** Warn if first activity starts before
  05:00 or last ends after 01:00 (next day).
- **Trip feasibility:** After `build_tours()`, check that each trip's
  travel time (from skim) fits within the gap between activities.

### 5b. Call `validate()` automatically in the simulation

In `_build_agent_plan()` (simulate.py), call `day_plan.validate()` after
scheduling and after discretionary planning. Log warnings but do not discard
the plan — collect statistics instead.

### 5c. Aggregate validation stats

At the end of `simulate()`, log a summary:
- Total households simulated / failed
- Total day plans validated / with warnings
- Most common warning types and counts

This gives immediate feedback on model quality without requiring separate
analysis. Write these stats to a `_validation_summary.json` alongside the
output parquets.

---

## 6. Improve Simulation Logging and Reproducibility

### 6a. Add structured logging

Replace `print()` calls in `simulate.py` with Python `logging`. Use levels:
- `INFO`: Household count, progress (every N households), final summary
- `WARNING`: Validation warnings, LLM fallbacks, skipped households
- `DEBUG`: Full prompts and responses (for debugging prompt issues)

### 6b. Store prompts and responses

The script already stores prompt text in parquet columns. Verify this works
for all 10 prompt steps (not just the main ones). This audit trail is critical
for prompt experimentation.

### 6c. Pin random seeds end-to-end

Verify that setting `simulation.seed` in config.yaml produces identical
zone-sampling and candidate-selection across runs (the LLM itself is
non-deterministic, but everything around it should be fixed). Add a note in
the README or config.yaml documenting what is and is not reproducible.

---

## 7. Config-Driven Prompt Experiments (no default changes)

The current `simulation.prompts` override system already supports per-step
customization. Prepare infrastructure for prompt experiments without changing
defaults.

### 7a. Add example alternative prompt configs

Create `workflow/prompt_configs/` with YAML files for 2-3 prompt variants
to try. Suggested experiments (to be specified further by the developer):

- **`trip_rate_fix.yaml`**: Override the `activities` step instructions to
  explicitly request a realistic number of out-of-home activities (e.g.
  "most adults make 2-4 out-of-home trips per day; retirees may make fewer").
- **`mode_realism.yaml`**: Override `mode_choice` instructions to emphasize
  distance-appropriate mode selection (e.g. "walking is only realistic for
  trips under 3 km; cycling under 10 km").
- **`scheduling_strictness.yaml`**: Override `scheduling` instructions to
  enforce minimum activity durations (e.g. "shopping: at least 15 min,
  leisure: at least 30 min").

**Important:** These are _experiment configs_, not replacements for the
defaults. The developer specifies them via
`simulation.prompts` in config.yaml or via `--config` pointing to an
alternative config file.

### 7b. Add a scenario comparison script

Create a lightweight script (`scripts/compare_scenarios.py`) that reads
two sets of output parquets and prints:
- Trip count delta
- Mode share comparison (table)
- Average trip distance comparison
- Activity count per agent comparison
- Validation warning count comparison

This makes it easy to evaluate prompt changes against the vanilla baseline.

---

## 8. Code Quality Cleanup

### 8a. Fix lazy imports in `household.py`

`create_client` is imported inside methods (lines ~137, ~294, ~480). Move to
top-level import for consistency with the rest of the codebase.

### 8b. Extract magic numbers to named constants

In `synthesis.py`:
- `4` (minimum school age) → `MIN_SCHOOL_AGE = 4`
- `0.1` (student rate scaling for 30-64) → `OLDER_ADULT_STUDENT_SCALE = 0.1`

In `day_plan.py`:
- `360.0` → `DEFAULT_DAY_START = 360.0` (06:00)
- `1380.0` → `DEFAULT_DAY_END = 1380.0` (23:00)

In `agent.py`:
- `15.0` (escort offset) → already in household.py, define once

### 8c. Add missing type parameters

Fix the generic `dict` and `list` annotations flagged by mypy (see 1b).

### 8d. Sync notebook with simulate.py

After all changes to `simulate.py`, update the corresponding cells in
`notebooks/simulate_walkthrough.ipynb` so they remain in sync (as required
by `CLAUDE.md`).

---

## 9. Documentation for Public Release

### 9a. Update README

- Describe what the model does (1 paragraph)
- Link to the webapp
- List prerequisites (Python 3.12+, API keys)
- Quick-start: `uv sync && uv run snakemake --cores 1 -s workflow/Snakefile`
- Link to the notebook walkthrough
- Note on LLM costs (approximate tokens per household)

### 9b. Add architecture diagram

Add a simple text-based or Mermaid diagram showing the simulation flow:
synthesis → persona → zone choice → activities → scheduling →
discretionary → joint/escort → vehicles → mode choice → tour building →
network assignment.

### 9c. Document config.yaml

Add inline comments to `workflow/config.yaml` explaining each parameter,
its valid range, and its effect. The file already has some comments but is
not comprehensive.

---

## 10. Pre-Release Checklist

Before tagging the beta:

- [ ] `uv run pytest` — all tests pass (0 errors, 0 failures)
- [ ] `uv run mypy src/` — 0 errors
- [ ] `uv run ruff check src tests` — all checks passed
- [ ] `uv run ruff format --check src tests` — no formatting issues
- [ ] Full pipeline runs end-to-end without crashes on 200 households
- [ ] Vanilla baseline stored with stats
- [ ] Validation summary shows < 20% of day plans with warnings
- [ ] Notebook runs top-to-bottom without errors
- [ ] README is accurate and complete
- [ ] No API keys or secrets in committed files
- [ ] Version bumped in `pyproject.toml` (0.1.0 → 0.2.0-beta)

---

## Execution Order

| Phase | Steps | Effort | Dependency |
|-------|-------|--------|------------|
| **A** | 0 (baseline snapshot) | Low | None — do first |
| **B** | 1a, 1b, 1c (fix tooling) | Low | None |
| **C** | 2a, 2b, 2c, 2d (LLM hardening) | Medium | None |
| **D** | 3a, 3b, 3c (time handling) | Low | None |
| **E** | 4a-4e (tests) | Medium | After C, D |
| **F** | 5a, 5b, 5c (validation) | Medium | After C |
| **G** | 6a, 6b, 6c (logging/repro) | Low | After C |
| **H** | 7a, 7b (prompt experiments) | Low | After A |
| **I** | 8a-8d (code quality) | Low | After C, D |
| **J** | 9a-9c (documentation) | Low | After all code changes |
| **K** | 10 (checklist) | Low | After everything |

Phases B, C, D can run in parallel. Phase E depends on C and D.
Phase H is independent and can start right after A.
