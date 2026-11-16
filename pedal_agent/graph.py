"""LangGraph agent loop around a RunRecord.

tone_analyst (LLM) -> approve_spec (human) -> planner (LLM) -> validate -> check -> router
  -> planner ... or -> feedback (human) -> planner (feedback text) | END (accept)

Graph state is the RunRecord as plain JSON plus a routing hint. Every node saves
runs/<run_id>.json before returning, so the dashboard can always read the latest
state. The two human review points use interrupt() with a SQLite checkpointer,
so a paused run can be resumed by another process (CLI now, Streamlit later).
Nodes that interrupt do all their work after interrupt() returns, because a
resumed node restarts from its beginning.
"""
import os
import re
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from pedal_agent.checker import check
from pedal_agent.config import REPO_ROOT, load_config
from pedal_agent.llm import LLM, LLMOutputError
from pedal_agent.prompts import planner_prompts, tone_prompts
from pedal_agent.router import RouterConfig, best_step, find_duplicate, route
from pedal_agent.schemas import (BenchmarkRef, Candidate, MetricTarget, PlannerDecision, RunRecord, Step,
                                 TargetSpec, ToneDraft, now)
from pedal_agent.validate import full_params, validate


class AgentState(TypedDict):
    run: dict       # RunRecord.model_dump(mode="json")
    goto: str       # next node chosen by the node that just ran


class RunStore:
    """runs/<run_id>.json, written atomically (temp file + rename)."""

    def __init__(self, runs_dir: Path | str | None = None):
        self.dir = Path(runs_dir) if runs_dir else REPO_ROOT / load_config()["paths"]["runs_dir"]
        self.dir.mkdir(parents=True, exist_ok=True)

    def path(self, run_id: str) -> Path:
        return self.dir / f"{run_id}.json"

    def save(self, run: RunRecord, attempts: int = 10, pause_s: float = 0.2) -> None:
        tmp = self.path(run.run_id).with_suffix(".json.tmp")
        tmp.write_text(run.model_dump_json(indent=2), encoding="utf-8")
        for i in range(attempts):
            try:
                os.replace(tmp, self.path(run.run_id))
                return
            except PermissionError:      # Windows: another process (scanner, indexer, reader) has the file open
                if i == attempts - 1:
                    raise
                time.sleep(pause_s)

    def load(self, run_id: str) -> RunRecord:
        return RunRecord.model_validate_json(self.path(run_id).read_text(encoding="utf-8"))


def open_checkpointer(store: RunStore) -> SqliteSaver:
    return SqliteSaver(sqlite3.connect(str(store.dir / "checkpoints.sqlite"), check_same_thread=False))


def slug(text: str, n: int = 4) -> str:
    return "-".join(re.findall(r"[a-z0-9]+", text.lower())[:n]) or "run"


def new_run(goal: str, llm: LLM, genre: str | None = None, mode: str = "agent",
            cfg: dict | None = None) -> RunRecord:
    cfg = cfg or load_config()
    project_id = slug(goal)
    return RunRecord(
        run_id=f"{datetime.now():%Y%m%d-%H%M%S}-{project_id}-{uuid.uuid4().hex[:4]}",
        project_id=project_id, model_id=llm.model_id, effort=llm.effort, mode=mode, status="running",
        spec=TargetSpec(goal_text=goal, genre=genre, targets=[]),
        sim_budget=cfg["run"]["sim_budget"],
        price_in_per_mtok=cfg["llm"]["price_in_per_mtok"] if llm.model_id == cfg["llm"]["model_id"] else 0.0,
        price_out_per_mtok=cfg["llm"]["price_out_per_mtok"] if llm.model_id == cfg["llm"]["model_id"] else 0.0,
    )


def new_benchmark_run(spec: TargetSpec, ref: BenchmarkRef, llm: LLM, mode: str = "agent",
                      seed: int | None = None, cfg: dict | None = None) -> RunRecord:
    """A run on a pre-approved benchmark spec: no Tone Analyst, common start step, benchmark stop rules."""
    cfg = cfg or load_config()
    spec = spec.model_copy(update={"approved": True, "approved_at": spec.approved_at or now()})
    real = llm.model_id == cfg["llm"]["model_id"]
    return RunRecord(
        run_id=f"{datetime.now():%Y%m%d-%H%M%S}-{ref.set}-{ref.target_id}-{mode}-{uuid.uuid4().hex[:4]}",
        project_id=f"benchmark-{ref.set}", model_id=llm.model_id, effort=llm.effort, mode=mode,
        status="running", spec=spec, sim_budget=cfg["run"]["sim_budget"], seed=seed, benchmark=ref,
        price_in_per_mtok=cfg["llm"]["price_in_per_mtok"] if real else 0.0,
        price_out_per_mtok=cfg["llm"]["price_out_per_mtok"] if real else 0.0,
    )


def _fmt(v) -> str:
    return f"{v:.3g}" if isinstance(v, float) else str(v)


def describe_change(prev: Candidate | None, new: Candidate) -> str:
    """Short step title from the chain difference, e.g. 'drive 0.5 → 0.7'."""
    ids = [b.block_id for b in new.chain]
    if prev is None:
        return "Chose " + " → ".join(ids)
    old_ids = [b.block_id for b in prev.chain]
    if ids == old_ids:
        diffs = []
        for a, b in zip(prev.chain, new.chain):
            pa, pb = full_params(a), full_params(b)
            prefix = f"{b.block_id}." if len(ids) > 1 else ""
            diffs += [f"{prefix}{k} {_fmt(pa[k])} → {_fmt(pb[k])}" for k in pb if pa[k] != pb[k]]
        return "; ".join(diffs) or "No change"
    added = [b for b in ids if b not in old_ids]
    removed = [b for b in old_ids if b not in ids]
    if added and removed:
        return f"Swapped {', '.join(removed)} → {', '.join(added)}"
    if added:
        return f"Added {', '.join(added)}"
    if removed:
        return f"Removed {', '.join(removed)}"
    return "Reordered chain: " + " → ".join(ids)


def build_graph(llm: LLM, store: RunStore, checkpointer, router_cfg: RouterConfig | None = None):
    rcfg = router_cfg or RouterConfig.from_config()

    def load(state: AgentState) -> RunRecord:
        return RunRecord.model_validate(state["run"])

    def commit(run: RunRecord, goto: str) -> dict:
        store.save(run)
        return {"run": run.model_dump(mode="json"), "goto": goto}

    def add_step(run: RunRecord, **kw) -> Step:
        step = Step(n=len(run.steps) + 1, **kw)
        run.steps.append(step)
        return step

    def fail(run: RunRecord, where: str, err: LLMOutputError) -> dict:
        add_step(run, agent="router", action="stop", title=f"Error in {where}", why=str(err), llm=err.usage)
        run.status, run.stop_reason = "stopped", "error"
        return commit(run, "end")

    def last_valid(run: RunRecord, before: int) -> Candidate | None:
        """Candidate of the latest valid proposal before step n=`before`: a planner step that passed
        Validate, or the benchmark start step (router, initial_chain)."""
        steps = [s for s in run.steps if s.agent in ("planner", "router") and s.n < before
                 and s.candidate is not None and not s.validation_errors]
        return steps[-1].candidate if steps else None

    def benchmark_start(state: AgentState) -> dict:
        """Benchmark runs: pre-approved spec, then the common start chain at its defaults (1 simulation)."""
        run = load(state)
        b = run.benchmark
        add_step(run, agent="human", action="human_approve_spec",
                 title="Target spec approved (benchmark spec, pre-approved)",
                 why=f"benchmark {b.set} {b.target_id}, category {b.category}")
        cand = Candidate(chain=b.start_chain, rationale="common benchmark start (defaults)")
        step = add_step(run, agent="router", action="initial_chain",
                        title="Benchmark start: " + " → ".join(x.block_id for x in b.start_chain) + " (defaults)",
                        why=cand.rationale, candidate=cand)
        step.report = check(cand, run.spec)
        run.sims_used += 1
        run.best_step = best_step(run).n
        run.status = "running"
        return commit(run, "router")

    def tone_analyst(state: AgentState) -> dict:
        run = load(state)
        system, user = tone_prompts(run.spec.goal_text, run.spec.genre, run.spec.test_signal)
        try:
            draft, usage = llm.generate("tone_analyst", system, user, ToneDraft)
        except LLMOutputError as e:
            return fail(run, "tone_analyst", e)
        run.spec.targets = draft.targets
        add_step(run, agent="tone_analyst", action="tone_analyst",
                 title=f"Target spec drafted ({len(draft.targets)} targets)", why=draft.rationale, llm=usage)
        run.status = "awaiting_spec_approval"
        return commit(run, "approve_spec")

    def approve_spec(state: AgentState) -> dict:
        run = load(state)
        answer = interrupt({"kind": "approve_spec", "run_id": run.run_id,
                            "spec": run.spec.model_dump(mode="json")})
        if answer.get("action") == "reject":
            add_step(run, agent="human", action="stop", title="Target spec rejected", why=answer.get("why", ""))
            run.status, run.stop_reason = "stopped", "human_review"
            return commit(run, "end")
        edited = answer.get("targets") is not None
        if edited:
            run.spec.targets = [MetricTarget.model_validate(t) for t in answer["targets"]]
        run.spec.approved, run.spec.approved_at = True, now()
        add_step(run, agent="human", action="human_approve_spec",
                 title="Target spec approved" + (" (edited)" if edited else ""), why=answer.get("why", ""))
        run.status = "running"
        return commit(run, "planner")

    def planner(state: AgentState) -> dict:
        run = load(state)
        system, user = planner_prompts(run)
        try:
            decision, usage = llm.generate("planner", system, user, PlannerDecision)
        except LLMOutputError as e:
            return fail(run, "planner", e)
        add_step(run, agent="planner", action=decision.action, title="Proposed chain", why=decision.rationale,
                 candidate=decision.to_candidate(), llm=usage)
        return commit(run, "validate")

    def validate_node(state: AgentState) -> dict:
        run = load(state)
        step = run.steps[-1]
        prev = last_valid(run, step.n)
        res = validate(step.candidate, step.action, [b.block_id for b in prev.chain] if prev else None, run.mode)
        step.warnings = res.warnings
        if not res.ok:
            step.validation_errors = res.errors
            step.title = f"Rejected proposal ({len(res.errors)} error{'s' * (len(res.errors) > 1)})"
            return commit(run, "router")
        step.candidate, step.action = res.candidate, res.action
        step.title = describe_change(prev, res.candidate)
        dup = find_duplicate(run, res.candidate)
        if dup is not None:
            step.duplicate_of = dup
            step.title += f" (same as step {dup}, not simulated)"
            return commit(run, "router")
        return commit(run, "check")

    def check_node(state: AgentState) -> dict:
        run = load(state)
        step = run.steps[-1]
        step.report = check(step.candidate, run.spec)
        run.sims_used += 1
        run.best_step = best_step(run).n
        return commit(run, "router")

    def router(state: AgentState) -> dict:
        run = load(state)
        reason = route(run, rcfg)
        if reason is None:
            return commit(run, "planner")
        best = run.best
        why = f"{run.sims_used}/{run.sim_budget} simulations used"
        if best:
            why += f"; best: step {best.n}, score {best.report.score:.3g}, {best.report.n_pass}/{len(best.report.results)} targets pass"
        add_step(run, agent="router", action="stop", title=f"Stopped: {reason}", why=why)
        run.status, run.stop_reason = "awaiting_feedback", reason
        return commit(run, "feedback")

    def feedback(state: AgentState) -> dict:
        run = load(state)
        answer = interrupt({"kind": "feedback", "run_id": run.run_id, "stop_reason": run.stop_reason,
                            "best_step": run.best_step})
        if answer.get("action") == "accept":
            add_step(run, agent="human", action="human_accept", title="Design accepted", why=answer.get("why", ""))
            run.status, run.stop_reason = "accepted", "human_accept"
            return commit(run, "end")
        add_step(run, agent="human", action="human_feedback", title="Feedback", why=answer["text"])
        run.sim_budget += rcfg.feedback_extra_sims
        run.status, run.stop_reason = "running", None
        return commit(run, "planner")

    g = StateGraph(AgentState)
    for name, fn in [("tone_analyst", tone_analyst), ("approve_spec", approve_spec), ("planner", planner),
                     ("validate", validate_node), ("check", check_node), ("router", router), ("feedback", feedback)]:
        g.add_node(name, fn)
    goto = lambda state: state["goto"]  # noqa: E731
    g.add_node("benchmark_start", benchmark_start)
    g.add_conditional_edges(START, lambda state: "benchmark_start" if state["run"].get("benchmark") else "tone_analyst",
                            {"benchmark_start": "benchmark_start", "tone_analyst": "tone_analyst"})
    g.add_edge("benchmark_start", "router")
    g.add_conditional_edges("tone_analyst", goto, {"approve_spec": "approve_spec", "end": END})
    g.add_conditional_edges("approve_spec", goto, {"planner": "planner", "end": END})
    g.add_conditional_edges("planner", goto, {"validate": "validate", "end": END})
    g.add_conditional_edges("validate", goto, {"check": "check", "router": "router"})
    g.add_edge("check", "router")
    g.add_conditional_edges("router", goto, {"planner": "planner", "feedback": "feedback"})
    g.add_conditional_edges("feedback", goto, {"planner": "planner", "end": END})
    return g.compile(checkpointer=checkpointer)


class Agent:
    """Start and resume runs. The CLI uses this now; the Streamlit UI will reuse it."""

    def __init__(self, llm: LLM, store: RunStore | None = None, router_cfg: RouterConfig | None = None):
        self.llm, self.store = llm, store or RunStore()
        self.checkpointer = open_checkpointer(self.store)
        self.graph = build_graph(llm, self.store, self.checkpointer, router_cfg)

    def _invoke(self, run_id: str, value) -> dict | None:
        """Run until the next pause; return its payload (None when the run has ended)."""
        try:
            result = self.graph.invoke(value, {"configurable": {"thread_id": run_id}})
        except Exception as e:  # infrastructure failure: mark the run file, then re-raise for the caller
            run = self.store.load(run_id)
            run.steps.append(Step(n=len(run.steps) + 1, agent="router", action="stop",
                                  title="Infrastructure error", why=f"{type(e).__name__}: {e}"))
            run.status, run.stop_reason = "stopped", "infra_error"
            self.store.save(run)
            raise
        pending = result.get("__interrupt__")
        return pending[0].value if pending else None

    def start(self, run: RunRecord) -> dict | None:
        self.store.save(run)
        return self._invoke(run.run_id, {"run": run.model_dump(mode="json"), "goto": ""})

    def resume(self, run_id: str, answer: dict) -> dict | None:
        return self._invoke(run_id, Command(resume=answer))

    def close(self) -> None:
        self.checkpointer.conn.close()
