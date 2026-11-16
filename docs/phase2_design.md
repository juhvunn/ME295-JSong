# Phase 2 design: the agent on the command line

Status: **draft for approval** (2026-11-16). Target: Phase 2 of `docs/DASHBOARD_SPEC.md`.
Nothing in this document is implemented yet.

**Goal.** `python -m pedal_agent run --goal "..."` goes from a tone description to a checked
pedal chain and writes a valid `RunRecord` to `runs/<run_id>.json` after every step. There is
no UI. The two human review points use the same LangGraph pause/resume mechanism that the
Streamlit UI will reuse in Phase 5.

## 1. The graph

```
START → tone_analyst (LLM) → approve_spec (human pause)
          approve → planner        reject → END (status=stopped)
planner (LLM) → validate (code) ── invalid ──────────────→ planner (errors in prompt, no sim used)
                     │ valid
                     ├─ duplicate of an earlier candidate → planner ("already tried: step n")
                     ▼
                  check (code: checker.check → CheckReport, sims_used += 1)
                     ▼
                  router (code) ── continue ──→ planner
                     │ stop (all_pass | budget | stall | duplicate)
                     ▼
                  feedback (human pause) ── text → planner (Step action=human_feedback)
                                         └─ accept → END (status=accepted)
```

| Node | Kind | Reads | Writes (as a `Step` in the RunRecord) |
|---|---|---|---|
| tone_analyst | LLM | goal, genre, metric guide, typical_metrics | `spec` (TargetSpec), step `tone_analyst` |
| approve_spec | human | spec | `spec.approved`, step `human_approve_spec`; edited targets allowed |
| planner | LLM | see section 4 | `PlannerDecision` → step with `candidate`, action = decision action |
| validate | code | decision, catalog, mode | errors/warnings into the step; snapped values into the candidate |
| check | code | candidate, spec | `report` on the planner's step; `sims_used`, `best_step` |
| router | code | history, budget | `status`, `stop_reason`, step `stop` |
| feedback | human | best result | step `human_feedback` or `human_accept` |

`status` follows the state machine in DASHBOARD_SPEC section 2: `awaiting_spec_approval` →
`running` → `awaiting_feedback` → `accepted`; any exception → `stopped` with `stop_reason=error`.

## 2. Pause/resume and saving

- **LangGraph** (installed: `langgraph` 1.2.22): `interrupt(payload)` inside `approve_spec` and
  `feedback`; resume with `graph.invoke(Command(resume=answer), config)` using
  `thread_id = run_id`. I will re-check the current LangGraph docs before writing this code.
- **Checkpointer:** a SQLite checkpointer (`runs/checkpoints.sqlite`, needs the
  `langgraph-checkpoint-sqlite` package). Unlike the in-memory one, it lets a *different process*
  resume a paused run, which the Streamlit UI will need. The CLI behaves the same either way.
- **RunRecord file:** every node ends by writing `runs/<run_id>.json` (written to a temp file,
  then renamed, so the dashboard never reads a half-written file). The RunRecord is the single
  source of truth. It replaces the old JSONL session memory (`memory.py`), because each `Step`
  already holds candidate, report, rationale and action (= change type).
- **Simulation scratch files** (netlists, ngspice output) move from `runs/<sim_id>/` to
  `runs/sims/<sim_id>/`, so `runs/` holds only RunRecords and the checkpoint DB at the top level.

## 3. LLM calls

- Model and effort are read from `config.yaml` (`claude-opus-5-5`, `effort: medium`) and copied
  into `RunRecord.model_id/effort`. No temperature (not settable); no forced tool use.
- **Structured outputs are available** (`client.messages.parse(..., output_format=PydanticModel)`,
  checked in the installed `anthropic` 2.8.0 SDK). The response is validated with Pydantic. On a
  failure (invalid output, `max_tokens`), retry **once** with the error message appended, then
  stop the run with `stop_reason=error`. A refusal stops the run immediately.
- **Schema restriction:** structured outputs cannot express free-form dicts such as
  `BlockInstance.params: dict[str, float|str]`. The LLM therefore returns params as a list of
  `{name, value}` pairs, and code converts them into `BlockInstance`.
- **API key:** `ANTHROPIC_API_KEY` from the environment or `.env` (already in `.gitignore`); never logged.
- **Token accounting (new fields in `schemas.py`):**
  ```python
  class LLMUsage(BaseModel):
      node: Literal["tone_analyst", "planner"]
      model_id: str; effort: str
      input_tokens: int; output_tokens: int
      attempts: int                  # 1, or 2 after a retry (tokens summed)
  Step.llm: Optional[LLMUsage] = None
  RunRecord.cost_usd -> property     # prices per MTok from config.yaml (llm.price_in/price_out)
  ```
  Prices go in `config.yaml` (Opus 5.5: $4 in / $20 out per million tokens), not in code.

## 4. Agent inputs and outputs

**Catalog** (generated from every `blocks/*/block.yaml`, about 1 line per param):
`id, category, name, character, chain_hint, params (type, min/max or choices, default), typical_metrics`.
No netlists, no schematics.

**Tone Analyst** → `TargetSpec` with names from `schemas.MetricName` only:

| Metric | Meaning given in the guide |
|---|---|
| `gain_1k_db` | small-signal gain at 1 kHz (loudness / how hard it drives the amp) |
| `thd_pct` | total harmonic distortion at the test signal (clean ≈ <1 %, breakup ≈ 2–10 %, fuzz ≫ 10 %) |
| `ac_peak_hz` / `ac_peak_db` | where the frequency response peaks and by how much (mid hump, brightness) |
| `even_odd` | even/odd harmonic ratio (asymmetric "warm" clipping ≫ 0, symmetric ≈ 0) |
| `out_pk_v` | output peak voltage into the 1 MΩ amp input |

The **typical_metrics** of each block (section 5) are given as numeric anchors, so ranges are
realistic for this library.

**Planner** → new `PlannerDecision`:
```python
class ParamValue(BaseModel): name: str; value: float | str
class ProposedBlock(BaseModel): block_id: str; params: list[ParamValue]
class PlannerDecision(BaseModel):
    action: Literal["initial_chain", "adjust_params", "swap_block", "add_block", "remove_block"]
    chain: list[ProposedBlock]        # the full proposed chain, pickup → amp
    rationale: str                    # short; shown in the Design choices panel
```
Planner prompt contents: approved targets; catalog; the latest CheckReport as a compact table
`(metric, target lo–hi, measured, status)`; the best result so far (step n, chain, score); the last
3 attempts (action, chain, score or validation errors); any human feedback; sims remaining. **No
waveforms or netlists.** The step's `title` (e.g. "Drive 0.50 → 0.70") is generated by code from
the difference between chains, not written by the LLM.

## 5. Deterministic parts

**typical_metrics** (one-off script, results written into each `block.yaml`): run the Checker on
each block's defaults at the standard test signal (1 kHz, 300 mV EMF), once per `D_clip` /
`Q_model` choice:
```yaml
typical_metrics:
  D_clip=si:  {gain_1k_db: 13.8, thd_pct: 8.4, ac_peak_hz: 873, ...}
  D_clip=led: {...}
```
These come from **placeholder models** and must be regenerated when real models arrive.

**Validate** (no simulation budget used):
- errors: unknown block id; unknown param name; number outside min/max (pots 0–1); invalid choice;
  chain length not 1–3; same block twice; in `baseline_fixed_topology` mode, any action other than
  `adjust_params` after the first chain, or a changed chain (block ids/order).
- fixes recorded as warnings: component values snapped to the nearest value of their E-series
  inside min/max (e.g. C3 50n → 47n).
- warnings only: `fuzz_ff_si` not first in the chain (its `chain_hint`).
- On errors, the planner step is kept with the errors and no report, and the errors go back to
  the Planner.

**Multi-block Checker:** one netlist with the same pickup model, 9 V supply and 1 MΩ load;
blocks connected `in → X1 → n1 → X2 → n2 → X3 → out`. DC checks are probed per block
(`v(x2.vr)` etc.), and model text is pasted once. Metrics are measured at the chain output.
Single-block results must stay identical (the existing 4 checker tests keep passing).

**Router** (in this order):
1. `all_pass`: every target passes.
2. `budget`: `sims_used >= sim_budget` (default **12**, `config.yaml`).
3. `stall`: the best score has not improved in the last **3** checks.
4. `duplicate`: see decision B below.

Safety net: at most `2 × sim_budget` Planner calls per run (invalid and duplicate proposals don't
use sims, so this prevents an endless loop). Hitting it stops with `stop_reason=budget`.

## 6. Command line

```
python -m pedal_agent run --goal "..." [--genre ...] [--auto-approve] [--no-feedback]
                          [--mode agent|baseline_fixed_topology] [--llm real|fake]
```
- Without `--auto-approve`: print the target table; ask **a**pprove / **e**dit / **r**eject. Edit
  asks per target for new lo/hi (Enter keeps the value).
- At the end (unless `--no-feedback`): print the best chain and its result table, then ask for
  feedback text or `accept`.
- Always printed at the end: run file path, `stop_reason`, sims used, topology changes, tokens and cost.
- `--llm fake`: a scripted stand-in for both LLM nodes (fixed TargetSpec and a fixed list of
  Planner decisions, no API calls, identical results every run). Token counts are 0 and
  `model_id="fake"`.

## 7. Tests

All with `--llm fake` except the last one:

| Test | Checks |
|---|---|
| validate | rejects unknown block, out-of-range param, invalid choice, duplicate block, chain change in baseline mode; snaps E-series; fuzz-not-first is a warning |
| multi-block checker | `fuzz_ff_si → od_ts808` simulates and passes DC checks for both blocks |
| router | stops on all_pass, budget, stall, duplicate (built from hand-made histories, no sims) |
| full fake run | CLI run with `--auto-approve --no-feedback` writes a RunRecord that validates against `schemas.py`; paused-run resume works |
| real run | skipped unless `ANTHROPIC_API_KEY` is set: `--goal "warm mid-forward overdrive with light breakup" --auto-approve --no-feedback`; prints the result table and token cost |

**Rough cost of the real run:** 1 Tone Analyst call + up to ~12–24 Planner calls with a few
thousand tokens each: about **$1–2** at Opus 5.5 prices (to be measured, not guaranteed).

## 8. Order of work

Each step ends with its tests and a short report to you; commits only after your OK.
1. `schemas.py` additions (LLMUsage, PlannerDecision) and config keys (sim_budget, prices)
2. typical_metrics script and filled `block.yaml`s
3. multi-block Checker
4. validate
5. router
6. fake LLM
7. graph + CLI (`pedal_agent/__main__.py`)
8. real LLM nodes
9. remaining tests, LOG.md entry, remove the old pre-Phase-2 loop (`agents/graph.py`, `agents/llm.py`,
   `memory.py`, `tools/validate.py`, `blocks/block_library.yaml`, `tests/test_agent_graph.py`) and
   update CLAUDE.md to match.

## 9. Decisions for you

- **A. SQLite checkpointer** (adds one small package; needed later for the UI) instead of the in-memory one. *Recommended: yes.*
- **B. Duplicates.** The first duplicate skips the simulation and tells the Planner. A *second
  duplicate in a row* stops the run with `stop_reason=duplicate`. (The alternative is to stop on
  the very first duplicate, which wastes a run on one repeated guess.) *Recommended: second in a row.*
- **C. Baseline mode.** The Planner picks the initial chain freely (`initial_chain`), and after that
  only `adjust_params` on that same chain is allowed. *Recommended: yes.* Note that CLAUDE.md's
  third baseline is a grid/random parameter search *without* an LLM. That is a separate Phase 3
  item, not this mode.
- **D. Retire the old loop** (`memory.py` JSONL and toy `block_library.yaml`) in step 9, with
  CLAUDE.md updated so the RunRecord replaces the JSONL memory. *Recommended: yes.*
- **E. Real-run test cost:** about $1–2 per run with your API key; it only runs when you set the key.
