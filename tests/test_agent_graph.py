"""LangGraph design loop with a scripted fake LLM (no API calls)."""
from types import SimpleNamespace

import pytest
from langgraph.types import Command

from pedal_agent.agents.graph import PlannerDecision, build_graph
from pedal_agent.agents.llm import AnthropicLLM, LLMOutputError
from pedal_agent.memory import SessionMemory
from pedal_agent.tools.validate import validate_circuit
from tests.test_rc_lowpass import FC, ngspice_available

needs_ngspice = pytest.mark.skipif(not ngspice_available(), reason="ngspice executable from config.yaml not found")


class FakeLLM:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.prompts = []

    def generate(self, system, prompt, schema):
        self.prompts.append(prompt)
        return schema(**self.decisions.pop(0))


def propose(r1, c1, change_type="values"):
    return {"action": "propose", "block": "diode_clipper", "values": {"R1": r1, "C1": c1},
            "change_type": change_type, "rationale": "test"}


STOP = {"action": "stop", "change_type": "values", "rationale": "test"}
TARGETS = [{"metric": "f_minus3db_hz", "target": FC, "tol_rel": 0.02}]


def run(llm, memory, max_sims=5, max_steps=5, approve=True):
    graph = build_graph(llm, memory)
    config = {"configurable": {"thread_id": "t1"}}
    paused = graph.invoke({"targets": TARGETS, "max_sims": max_sims, "max_steps": max_steps}, config)
    payload = paused["__interrupt__"][0].value
    final = graph.invoke(Command(resume=approve), config)
    return payload, final


def test_validate_circuit():
    assert validate_circuit({"block": "diode_clipper", "values": {"R1": 4.7e3, "C1": 10e-9}}) == []
    assert "unknown block" in validate_circuit({"block": "fuzz", "values": {}})[0]
    assert "no netlist template" in validate_circuit({"block": "opamp_gain", "values": {}})[0]
    errors = validate_circuit({"block": "diode_clipper", "values": {"R1": 1e9, "X": 1.0}})
    assert any("missing parameter C1" in e for e in errors)
    assert any("unexpected parameter X" in e for e in errors)
    assert any("R1=1e+09" in e and "outside" in e for e in errors)


def test_invalid_candidate_is_recorded_without_spending_a_simulation(tmp_path):
    memory = SessionMemory(tmp_path / "memory.jsonl")
    llm = FakeLLM([propose(1e9, 10e-9), STOP])
    payload, final = run(llm, memory)

    records = memory.records()
    assert [r["status"] for r in records] == ["invalid"]
    assert "outside" in records[0]["violations"][0]
    assert final.get("n_sims", 0) == 0
    assert payload == {"best": None, "n_sims": 0, "n_candidates": 1}
    assert final["approved"] is True
    # The second Planner call saw the validation error.
    assert "outside" in llm.prompts[1]


@needs_ngspice
def test_value_revision_reaches_rc_target(tmp_path):
    memory = SessionMemory(tmp_path / "memory.jsonl")
    # Small-signal AC: diodes are off, so the clipper is an RC low-pass at 1/(2*pi*R1*C1).
    llm = FakeLLM([propose(4.7e3, 10e-9), propose(10e3, 10e-9)])
    payload, final = run(llm, memory)

    first, second = memory.records()
    assert first["status"] == "evaluated" and first["violations"][0]["error"] > 0.02
    assert second["status"] == "met" and second["parent_id"] == first["id"]
    assert second["change_type"] == "values"
    assert payload["best"]["id"] == second["id"] and payload["n_sims"] == 2
    assert final["approved"] is True


@needs_ngspice
def test_simulation_budget_stops_the_loop(tmp_path):
    memory = SessionMemory(tmp_path / "memory.jsonl")
    llm = FakeLLM([propose(4.7e3, 10e-9)])  # a second Planner call would fail: list is empty
    payload, final = run(llm, memory, max_sims=1, approve=False)
    assert [r["status"] for r in memory.records()] == ["evaluated"]
    assert payload["n_sims"] == 1 and final["approved"] is False


def fake_client(responses):
    calls = []

    def parse(**kwargs):
        calls.append(kwargs)
        return responses.pop(0)

    return SimpleNamespace(messages=SimpleNamespace(parse=parse)), calls


LLM_CONFIG = {"llm": {"model_id": "test-model", "max_retries": 2, "max_tokens": 100, "effort": "low"}}


def test_anthropic_llm_retries_then_returns_parsed_output():
    ok = PlannerDecision(**STOP)
    client, calls = fake_client([
        SimpleNamespace(stop_reason="max_tokens", parsed_output=None),
        SimpleNamespace(stop_reason="end_turn", parsed_output=ok),
    ])
    assert AnthropicLLM(LLM_CONFIG, client).generate("sys", "go", PlannerDecision) is ok
    assert [c["model"] for c in calls] == ["test-model", "test-model"]
    assert "previous answer was invalid" in calls[1]["messages"][0]["content"]


def test_anthropic_llm_gives_up_after_max_retries():
    bad = SimpleNamespace(stop_reason="max_tokens", parsed_output=None)
    client, calls = fake_client([bad, bad])
    with pytest.raises(LLMOutputError):
        AnthropicLLM(LLM_CONFIG, client).generate("sys", "go", PlannerDecision)
    assert len(calls) == 2


def test_anthropic_llm_requires_pinned_model():
    with pytest.raises(ValueError):
        AnthropicLLM({"llm": {**LLM_CONFIG["llm"], "model_id": "MODEL_ID_PLACEHOLDER"}}, client=object())
