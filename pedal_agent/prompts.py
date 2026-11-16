"""Prompt text for the LLM nodes, built from the RunRecord and the block library.

Only compact numbers go to the LLM: the catalog, target tables, CheckReport
tables and short history lines. Never waveforms, plots or netlists.
"""
import json

from pedal_agent.build import BLOCKS_DIR, load_block
from pedal_agent.router import best_step
from pedal_agent.schemas import Candidate, CheckReport, RunRecord, Step, TargetSpec
from pedal_agent.validate import allow_unvalidated_default, allowed_choices

METRIC_GUIDE = {
    "gain_1k_db": "small-signal gain at 1 kHz in dB (how loud / how hard it drives the amp)",
    "thd_pct": "total harmonic distortion in % at the test signal (clean < 1, light breakup 2-10, "
               "heavy overdrive 10-30, fuzz > 30)",
    "ac_peak_hz": "frequency of the frequency-response peak in Hz (~700-1000 = mid hump, "
                  "> 2000 = bright, < 300 = bassy)",
    "ac_peak_db": "gain at the frequency-response peak in dB",
    "even_odd": "even/odd harmonic ratio (asymmetric clipping, warm/fuzzy > 0.3; symmetric ~ 0)",
    "out_pk_v": "output peak voltage in V into the 1 MOhm amp input (level knobs change it)",
}

TONE_SYSTEM = """You are the Tone Analyst for a guitar pedal design agent.
Translate the player's tone description into 3-6 measurable targets.
Use only these metric names: {names}. Give each target a lo and/or hi bound (leave the other
unbounded when only one side matters), a unit, a short label for a table, and weight 1 unless a
target is clearly central to the description.
The test signal is a {f0:g} Hz sine of {amp_mv:g} mV from a guitar pickup into the pedal chain,
measured at a 1 MOhm amp input. Use the typical metrics of the library blocks as anchors so that
the ranges are reachable. Ranges should be wide enough to allow several valid designs."""

PLANNER_SYSTEM = """You are the Planner for a guitar pedal design agent.
Propose a pedal chain (1-3 blocks from the catalog, each block at most once, signal order
pickup -> ... -> amp) whose measured metrics meet the approved targets.
Each call, return the full proposed chain and one action:
- initial_chain: the first proposal
- adjust_params: same blocks in the same order, different knob/part/choice values
- swap_block, add_block, remove_block: change the blocks
Knobs (type pot) are positions 0-1. Parts (type component) must stay inside min/max (SI units,
e.g. 4.7e-8 for 47 nF). Choices must be one of the listed values. Params you leave out keep
their defaults.
Use the measured results: status low/high says which way each metric must move. A simulation
costs budget; candidates identical to an earlier one are not simulated again.
Keep the rationale to one or two sentences."""


def catalog(include_typical: bool) -> list[dict]:
    """Compact block catalog; choices with unvalidated part models are left out unless allowed."""
    allow = allow_unvalidated_default()
    out = []
    for d in sorted(p for p in BLOCKS_DIR.iterdir() if (p / "block.yaml").is_file()):
        _, meta = load_block(d.name)
        params = {}
        for name, p in meta["params"].items():
            if p["type"] == "pot":
                params[name] = f"knob 0-1 ({p['taper']}), default {p['default']}"
            elif p["type"] == "choice":
                params[name] = f"choice {allowed_choices(p, allow)}, default {p['default']}"
                if p.get("recommended"):   # hint only: the Planner must set these params itself
                    params[name] += "; recommended settings when choosing (set them yourself): " + ", ".join(
                        f"{c} -> " + " ".join(f"{k}={v}" for k, v in rec.items()) for c, rec in p["recommended"].items())
            else:
                params[name] = f"part {p['min']}-{p['max']} ({p.get('series', 'any')}), default {p['value']}"
            if p.get("note"):
                params[name] += f"; {' '.join(str(p['note']).split())}"
        entry = {"id": meta["id"], "category": meta["category"], "name": meta["name"],
                 "character": " ".join(meta["character"].split()), "params": params}
        if meta.get("chain_hint"):
            entry["chain_hint"] = meta["chain_hint"]
        if include_typical:
            entry["typical_metrics_at_defaults"] = meta.get("typical_metrics", {})
        out.append(entry)
    return out


def tone_prompts(goal: str, genre: str | None, signal: dict) -> tuple[str, str]:
    system = TONE_SYSTEM.format(names=", ".join(METRIC_GUIDE), f0=signal["f0_hz"], amp_mv=signal["amp_v"] * 1e3)
    user = json.dumps({"tone_goal": goal, "genre": genre, "metric_guide": METRIC_GUIDE,
                       "library_blocks": catalog(include_typical=True)}, indent=1)
    return system, user


def _bounds(lo, hi) -> str:
    return f"{'-inf' if lo is None else f'{lo:g}'} .. {'inf' if hi is None else f'{hi:g}'}"


def report_table(spec: TargetSpec, report: CheckReport) -> list[dict]:
    by_name = {r.name: r for r in report.results}
    rows = [{"metric": t.name, "target": _bounds(t.lo, t.hi), "measured": round(by_name[t.name].value, 3),
             "status": by_name[t.name].status} for t in spec.targets if t.name in by_name]
    return rows


def chain_text(c: Candidate) -> list[dict]:
    return [{"block_id": b.block_id, "params": b.params} for b in c.chain]


def attempt_line(s: Step) -> dict:
    line = {"step": s.n, "action": s.action}
    if s.candidate:
        line["chain"] = chain_text(s.candidate)
    if s.validation_errors:
        line["rejected"] = s.validation_errors
    elif s.duplicate_of is not None:
        line["duplicate_of_step"] = s.duplicate_of
    elif s.report:
        line["score"] = round(s.report.score, 4)
        line["failed"] = [r.name for r in s.report.results if r.status != "pass"]
        if s.report.errors:
            line["errors"] = s.report.errors
    if s.warnings:
        line["warnings"] = s.warnings
    return line


def planner_prompts(run: RunRecord) -> tuple[str, str]:
    planned = [s for s in run.steps if s.agent == "planner"]
    checked = [s for s in planned if s.report is not None]
    best = best_step(run)
    feedback = [s.why for s in run.steps if s.action == "human_feedback"]
    ctx = {
        "mode": run.mode,
        "targets": [{"metric": t.name, "target": _bounds(t.lo, t.hi), "unit": t.unit, "label": t.label,
                     "weight": t.weight} for t in run.spec.targets],
        "catalog": catalog(include_typical=False),
        "simulations_remaining": run.sim_budget - run.sims_used,
    }
    if run.mode == "baseline_fixed_topology" and checked:
        ctx["rule"] = "baseline mode: keep the same blocks in the same order; only adjust_params is allowed"
    if checked:
        last = checked[-1]
        ctx["latest_result"] = {"step": last.n, "chain": chain_text(last.candidate),
                                "table": report_table(run.spec, last.report),
                                "score": round(last.report.score, 4), "dc_ok": last.report.dc_ok,
                                "errors": last.report.errors}
        ctx["best_so_far"] = {"step": best.n, "chain": chain_text(best.candidate),
                              "score": round(best.report.score, 4)}
    if planned:
        ctx["last_attempts"] = [attempt_line(s) for s in planned[-3:]]
    if feedback:
        ctx["human_feedback"] = feedback
        ctx["note"] = "the latest human feedback is the most important input now"
    return PLANNER_SYSTEM, json.dumps(ctx, indent=1)
