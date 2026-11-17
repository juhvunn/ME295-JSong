# Guitar Pedal Agent: Dashboard Spec (target for all backend work)

The dashboard mockup (claude.ai canvas "Pedal Agent Dashboard") is the final
target. Backend work is "done" when every panel below can be filled from
`runs/<run_id>.json` (a `RunRecord`, see `schemas.py`) plus the block library.

Rule: the UI only READS run files and calls the five actions in section 3.
All agent logic lives in the backend and runs (and is testable) without the UI.

## 1. Panel → data map

| Panel | Field(s) | Producer |
|---|---|---|
| Create new project | `Project.name/genre/describe/reference` | UI input |
| Saved circuits | `projects/*.json`, best `Step` of latest run: `n_pass / len(results)`, chain | store |
| Selected project header | `Project.name`, `spec.goal_text`, `status`, `best.report.n_pass` | graph |
| Signal chain | `best.candidate.chain[*].block_id/params` | Planner |
| Block schematic | `pedal_agent/schematics/<id>.py` rendered with resolved params | schematic (Phase 4) |
| Component list | `build.render_context(block_id, params)` + `block.yaml` (highlight = keys of `params`) | build |
| Design choices | `steps[*].n/action/title/why` | Tone Analyst, Planner, human |
| Test result: waveform, freq. response | `best.report.plots` | Checker |
| Test result: target table | `spec.targets` + `best.report.results` | Checker |
| Demo sound | `audio.dry/processed` | audio render (Phase 6) |
| Feedback | appends `Step(action="human_feedback")`, resumes graph | graph |
| Reference models | `blocks/*/block.yaml`: `category, name, character, source` | library |
| Agent run | `len(steps)`, `sims_used/sim_budget`, `topology_changes`, `stop_reason` | graph |
| Repeated runs | all runs of a project with same `spec`: success rate, median `sims_used` | eval script (Phase 3) |

## 2. Run status machine

```
awaiting_spec_approval --approve--> running --(all_pass|budget|stall|duplicate)--> awaiting_feedback
awaiting_feedback --feedback--> running        awaiting_feedback --accept--> accepted
any --error--> stopped
```
Human review points: spec approval, feedback/accept. The graph must pause there
(LangGraph interrupt + checkpointer; check current docs before implementing).

## 3. Backend actions the UI may call

| Action | Effect |
|---|---|
| `create_project(name, genre, describe, reference)` | writes `Project`, starts run → Tone Analyst → `awaiting_spec_approval`; refused while another run is active (one active run at a time, simple lock) |
| `approve_spec(run_id, edited_targets=None)` | stores approved `TargetSpec`, resumes graph |
| `send_feedback(run_id, text)` | appends feedback step, resumes Planner |
| `accept(run_id)` | `status=accepted`, triggers audio render |
| `export_design(run_id)` | accepted runs only, on the user's click: `exports/<run_id>/` with `netlist.cir` (the exact simulated netlist, SHA-256 checked against the Checker report; refused if it no longer reproduces), `bom.csv` (signal-path parts per block, pots with knob setting), `schematic_<n>_<block>.svg/.png` per block (pedal_agent/schematics, connections checked against the netlist, subcircuit verbatim in `netlist.cir`) and `summary.md`; never overwrites (`pedal_agent/export.py`) |
| `render_audio(run_id, clip)` | Phase 6 |

## 4. Fixed choices

- Model: `claude-opus-5-5`, effort pinned in `config.yaml` (temperature cannot be set; reliability = repeated runs).
- No forced tool use (unsupported); Planner output parsed and validated with Pydantic.
- Checker, Validate, Build, Router are deterministic code. Test signal: 1 kHz sine, 300 mV EMF through the pickup model in `harness.py`.

## 5. Phases and acceptance criteria

1. **Checker** (`checker.py`, done for single-block chains): `check(candidate, spec) -> CheckReport`; `pytest tests/test_checker.py` passes. Real component models replace `smoke_models.lib`.
2. **Graph on the command line**: `python -m pedal_agent run --goal "..." [--auto-approve]` writes a valid `RunRecord`; Validate rejects bad chains without using sim budget; multi-block chains supported in `checker.simulate`.
3. **Reliability + baseline**: `--repeats N` and `--mode baseline_fixed_topology` (Planner limited to `adjust_params`); summary table of success rate, sims used, score.
4. **Schematics**: `pedal_agent/schematics/<id>.py` per block (code, kept out of `blocks/`, which holds the block data the
   Checker reads), labels from the same resolved values as the netlist.
5. **Streamlit UI**: reproduces the mockup from `runs/example-jazz-christmas.json` first, then live runs via section 3.
6. **Audio**: DI clip (own recording) → transient sim → WAV, cached per accepted design.
