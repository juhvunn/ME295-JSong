"""Build an ILLUSTRATIVE example RunRecord: not an experimental result.
It mirrors the dashboard mockup ("Jazz Christmas") so the UI can be developed against a realistic file.
Tone Analyst and Planner text is hand-written (no LLM call); the Checker output is real, with the
configured model set (config.yaml models.set). Model ID and effort are read from config.yaml.
The dashboard marks runs whose run_id starts with "example-" as illustrative."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pedal_agent.schemas import *
from pedal_agent.checker import check
from pedal_agent.config import load_config

LABEL = ("ILLUSTRATIVE EXAMPLE - not an experimental result. Tone Analyst and Planner text are hand-written "
         "(no LLM call); the Checker output is real.")
cfg = load_config()

spec = TargetSpec(
    goal_text="Warm, mid-forward lead tone with light breakup when picking hard.",
    genre="Jazz", reference=None, approved=True, approved_at=now(),
    targets=[MetricTarget(name="gain_1k_db", lo=15, hi=22, unit="dB", label="Gain at 1 kHz"),
             MetricTarget(name="thd_pct", lo=2, hi=8, unit="%", label="THD (300 mV)"),
             MetricTarget(name="ac_peak_hz", lo=600, hi=1000, unit="Hz", label="Mid peak"),
             MetricTarget(name="even_odd", hi=0.5, label="Even / odd harmonics")])

c1 = Candidate(chain=[BlockInstance(block_id="od_ts808", params={"drive": 0.5})],
               rationale='Soft clipping and a mid hump fit "warm, mid-forward" best.')
c2 = Candidate(chain=[BlockInstance(block_id="od_ts808", params={"drive": 0.7})],
               rationale="Gain at 1 kHz was below the 15 dB floor.")
r1, r2 = check(c1, spec), check(c2, spec)

steps = [
    Step(n=1, agent="tone_analyst", action="tone_analyst", title="Target spec drafted",
         why=f"{LABEL} Four targets from the description."),
    Step(n=2, agent="human", action="human_approve_spec", title="Target spec approved", why=""),
    Step(n=3, agent="planner", action="initial_chain", title="Chose TS-808", why=c1.rationale, candidate=c1, report=r1),
    Step(n=4, agent="planner", action="adjust_params", title="Drive 0.50 → 0.70", why=c2.rationale, candidate=c2, report=r2),
]
best = min((s for s in steps if s.report), key=lambda s: s.report.score)
run = RunRecord(run_id="example-jazz-christmas", project_id="jazz-christmas",
                model_id=cfg["llm"]["model_id"], effort=cfg["llm"]["effort"], status="awaiting_feedback",
                stop_reason="human_review", spec=spec, steps=steps, best_step=best.n, sims_used=2)
out = Path(__file__).resolve().parents[1] / "runs" / f"{run.run_id}.json"
out.write_text(run.model_dump_json(indent=2), encoding="utf-8", newline="\n")
for s in steps:
    if s.report:
        print(s.title, {r.name: (round(r.value, 2), r.status) for r in s.report.results}, "score", round(s.report.score, 3))
print("wrote", out, "topology_changes", run.topology_changes)
