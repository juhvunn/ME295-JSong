"""AnthropicLLM with a stand-in client (no API calls): retries, token sums, refusals."""
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from pedal_agent.llm import AnthropicLLM, LLMOutputError
from pedal_agent.schemas import PlannerDecision

CFG = {"llm": {"model_id": "test-model", "effort": "low", "max_tokens": 100, "max_retries": 2}}
OK = PlannerDecision.model_validate({"action": "initial_chain", "rationale": "r",
                                     "chain": [{"block_id": "od_ts808", "params": []}]})


def resp(parsed, stop="end_turn", tin=100, tout=50):
    return SimpleNamespace(parsed_output=parsed, stop_reason=stop, stop_details=None,
                           usage=SimpleNamespace(input_tokens=tin, output_tokens=tout))


def client(*responses):
    calls, queue = [], list(responses)

    def parse(**kw):
        calls.append(kw)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return SimpleNamespace(messages=SimpleNamespace(parse=parse)), calls


def validation_error():
    try:
        PlannerDecision.model_validate({"action": "nope"})
    except ValidationError as e:
        return e


def test_success_records_model_effort_and_tokens():
    c, calls = client(resp(OK))
    out, usage = AnthropicLLM(CFG, c).generate("planner", "sys", "prompt", PlannerDecision)
    assert out is OK
    assert (usage.model_id, usage.effort, usage.input_tokens, usage.output_tokens, usage.attempts) == \
        ("test-model", "low", 100, 50, 1)
    kw = calls[0]
    assert kw["model"] == "test-model" and kw["output_format"] is PlannerDecision
    assert kw["output_config"] == {"effort": "low"} and kw["system"] == "sys"
    assert "temperature" not in kw and "tool_choice" not in kw


def test_retries_once_with_error_and_sums_tokens():
    c, calls = client(resp(None, stop="max_tokens", tin=100, tout=100), resp(OK, tin=120, tout=40))
    out, usage = AnthropicLLM(CFG, c).generate("planner", "sys", "prompt", PlannerDecision)
    assert out is OK and (usage.input_tokens, usage.output_tokens, usage.attempts) == (220, 140, 2)
    assert "previous answer was invalid" in calls[1]["messages"][0]["content"]
    assert "max_tokens" in calls[1]["messages"][0]["content"]


def test_validation_error_is_retried():
    c, calls = client(validation_error(), resp(OK))
    out, usage = AnthropicLLM(CFG, c).generate("planner", "sys", "prompt", PlannerDecision)
    assert out is OK and usage.attempts == 2 and len(calls) == 2


def test_gives_up_after_two_attempts_with_usage():
    c, calls = client(resp(None, stop="max_tokens"), resp(None, stop="max_tokens"))
    with pytest.raises(LLMOutputError, match="after 2 attempts") as info:
        AnthropicLLM(CFG, c).generate("planner", "sys", "prompt", PlannerDecision)
    assert len(calls) == 2 and info.value.usage.input_tokens == 200


def test_refusal_stops_immediately():
    c, calls = client(resp(None, stop="refusal"), resp(OK))
    with pytest.raises(LLMOutputError, match="refused") as info:
        AnthropicLLM(CFG, c).generate("planner", "sys", "prompt", PlannerDecision)
    assert len(calls) == 1 and info.value.usage.output_tokens == 50


def test_model_and_effort_come_from_config_yaml():
    llm = AnthropicLLM(client=object())
    assert (llm.model_id, llm.effort, llm.attempts) == ("claude-opus-5-5", "medium", 2)
