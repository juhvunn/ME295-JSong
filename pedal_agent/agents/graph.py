"""LangGraph design loop: Planner -> validate -> simulate/evaluate -> Planner ... -> human approval.

Only the Planner node calls the LLM. Validation, netlist building, simulation and
evaluation are deterministic tools; the Planner sees their results as numbers.
Every candidate is appended to session memory, invalid ones included, but only
simulations count against the budget.
"""
import json
import math
import operator
from typing import Annotated, Literal, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from pedal_agent.agents.llm import StructuredLLM
from pedal_agent.memory import SessionMemory
from pedal_agent.reference.build import build_block_netlist, load_protocol
from pedal_agent.tools.evaluate import check_targets, f_minus3db
from pedal_agent.tools.simulate import read_wrdata, simulate
from pedal_agent.tools.validate import load_block_library, validate_circuit

PLANNER_SYSTEM = """You are the Planner in a guitar preamp circuit design loop.
Propose one candidate circuit from the block catalog so that its measured metrics meet the targets.
Use only catalog blocks and keep every value inside its catalog range (SI units).
Each history entry shows a past candidate and its checker feedback as numbers:
error = (got - target) / target, and a target is met when |error| <= tol_rel.
Choose action "stop" when the targets are met or no further improvement is likely.
Set change_type to "topology" if you changed the block(s), "values" if you changed only component values."""


class PlannerDecision(BaseModel):
    action: Literal["propose", "stop"]
    block: str | None = Field(None, description="catalog block name; required when proposing")
    values: dict[str, float] = Field(default_factory=dict, description="component values in SI units")
    change_type: Literal["topology", "values"]
    rationale: str


class DesignState(TypedDict, total=False):
    targets: list[dict]
    max_sims: int
    max_steps: int
    n_sims: int
    n_steps: int
    decision: dict
    valid: bool
    history: Annotated[list[dict], operator.add]
    approved: bool


def worst_error(rec: dict) -> float:
    """Largest |relative error| over the targets; unmeasured metrics count as infinite."""
    return max((abs(v["error"]) if v["error"] is not None else math.inf for v in rec["violations"]),
               default=math.inf)


def build_graph(llm: StructuredLLM, memory: SessionMemory, checkpointer=None):
    library = load_block_library()
    protocol_version = load_protocol()["version"]
    catalog = {
        name: {"description": b["description"], "params": b["params"]}
        for name, b in library.items() if b.get("template")
    }

    def planner(state: DesignState) -> dict:
        history = state.get("history", [])
        prompt = json.dumps({
            "targets": state["targets"],
            "catalog": catalog,
            "simulations_remaining": state["max_sims"] - state.get("n_sims", 0),
            "history": [
                {k: r[k] for k in ("id", "blocks", "values", "status", "violations", "change_type")}
                for r in history
            ],
        }, indent=1)
        decision = llm.generate(PLANNER_SYSTEM, prompt, PlannerDecision)
        return {"decision": decision.model_dump(), "n_steps": state.get("n_steps", 0) + 1}

    def record(state: DesignState, status: str, metrics: dict, violations: list, run_id=None) -> dict:
        history, decision = state.get("history", []), state["decision"]
        rec = {
            "id": f"c{len(history) + 1:03d}",
            "parent_id": history[-1]["id"] if history else None,
            "blocks": [decision["block"]],
            "values": decision["values"],
            "protocol_version": protocol_version,
            "status": status,
            "metrics": metrics,
            "violations": violations,
            "rationale": decision["rationale"],
            "change_type": decision["change_type"],
            "run_id": run_id,
        }
        memory.append(rec)
        return {"history": [rec]}

    def validate(state: DesignState) -> dict:
        decision = state["decision"]
        errors = validate_circuit({"block": decision["block"], "values": decision["values"]}, library)
        if errors:
            return {**record(state, "invalid", {}, errors), "valid": False}
        return {"valid": True}

    def simulate_evaluate(state: DesignState) -> dict:
        decision = state["decision"]
        netlist = build_block_netlist(library[decision["block"]]["template"], decision["values"])
        res = simulate(netlist)
        n_sims = state.get("n_sims", 0) + 1
        if not res.ok:
            return {**record(state, "sim_failed", {}, [], res.run_id), "n_sims": n_sims}

        freq, gain_db = read_wrdata(res.run_dir / "ac.txt", n_vectors=1)
        try:
            f3 = f_minus3db(freq, gain_db[:, 0])
        except ValueError:
            f3 = None
        metrics = {"f_minus3db_hz": f3}
        rows = check_targets(metrics, state["targets"])
        status = "met" if all(r["met"] for r in rows) else "evaluated"
        return {**record(state, status, metrics, rows, res.run_id), "n_sims": n_sims}

    def approve(state: DesignState) -> dict:
        history = state.get("history", [])
        evaluated = [r for r in history if r["status"] in ("met", "evaluated")]
        answer = interrupt({
            "best": min(evaluated, key=worst_error) if evaluated else None,
            "n_sims": state.get("n_sims", 0),
            "n_candidates": len(history),
        })
        return {"approved": bool(answer)}

    def budget_left(state: DesignState) -> bool:
        return state.get("n_sims", 0) < state["max_sims"] and state.get("n_steps", 0) < state["max_steps"]

    def after_planner(state: DesignState) -> str:
        return "approve" if state["decision"]["action"] == "stop" else "validate"

    def after_validate(state: DesignState) -> str:
        if state["valid"]:
            return "simulate_evaluate"
        return "planner" if budget_left(state) else "approve"

    def after_evaluate(state: DesignState) -> str:
        if state["history"][-1]["status"] == "met" or not budget_left(state):
            return "approve"
        return "planner"

    graph = StateGraph(DesignState)
    graph.add_node("planner", planner)
    graph.add_node("validate", validate)
    graph.add_node("simulate_evaluate", simulate_evaluate)
    graph.add_node("approve", approve)
    graph.add_edge(START, "planner")
    graph.add_conditional_edges("planner", after_planner, ["validate", "approve"])
    graph.add_conditional_edges("validate", after_validate, ["simulate_evaluate", "planner", "approve"])
    graph.add_conditional_edges("simulate_evaluate", after_evaluate, ["planner", "approve"])
    graph.add_edge("approve", END)
    return graph.compile(checkpointer=checkpointer or InMemorySaver())
