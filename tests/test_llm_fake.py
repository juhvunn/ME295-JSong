"""FakeLLM: scripted, free, repeatable stand-in for both LLM nodes."""
import pytest

from pedal_agent.llm import FakeLLM, LLMOutputError
from pedal_agent.schemas import PlannerDecision, ToneDraft
from pedal_agent.validate import validate


def test_replays_script_in_order_with_zero_usage():
    llm = FakeLLM()
    tone, usage = llm.generate("tone_analyst", "sys", "goal", ToneDraft)
    assert [t.name for t in tone.targets] == ["gain_1k_db", "thd_pct", "ac_peak_hz", "even_odd"]
    assert (usage.node, usage.model_id, usage.input_tokens, usage.output_tokens) == ("tone_analyst", "fake", 0, 0)
    actions = [llm.generate("planner", "sys", f"p{i}", PlannerDecision)[0].action for i in range(5)]
    assert actions == ["initial_chain", "swap_block", "adjust_params", "adjust_params", "adjust_params"]
    assert [p for _, p in llm.calls] == ["goal", "p0", "p1", "p2", "p3", "p4"]


def test_exhausted_script_raises():
    llm = FakeLLM({"planner": []})
    with pytest.raises(LLMOutputError, match="exhausted"):
        llm.generate("planner", "sys", "p", PlannerDecision)


def test_two_fake_llms_give_identical_output():
    a, b = FakeLLM(), FakeLLM()
    for _ in range(5):
        assert a.generate("planner", "", "", PlannerDecision)[0] == b.generate("planner", "", "", PlannerDecision)[0]


def test_default_script_exercises_validate_paths():
    llm = FakeLLM()
    decisions = [llm.generate("planner", "", "", PlannerDecision)[0] for _ in range(5)]
    prev = None
    outcomes = []
    for d in decisions:
        res = validate(d.to_candidate(), d.action, prev)
        outcomes.append(res.action if res.ok else "invalid")
        if res.ok:
            prev = [b.block_id for b in res.candidate.chain]
    assert outcomes == ["initial_chain", "swap_block", "invalid", "adjust_params", "adjust_params"]
