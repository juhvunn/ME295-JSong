"""ClaudeSDKLLM (docs/agent_sdk_plan.md) with a stand-in for claude_agent_sdk.query: no network, no token use."""
from pathlib import Path

import pytest
from claude_agent_sdk import AssistantMessage, ProcessError, ResultMessage, ToolUseBlock

import pedal_agent.llm as llm_mod
from pedal_agent.config import REPO_ROOT, load_config
from pedal_agent.llm import ClaudeSDKLLM, LLMInfraError, LLMOutputError, UsageLimitError, make_real_llm
from pedal_agent.schemas import PlannerDecision

TOKEN = "sk-ant-oat01-FAKE-TOKEN-for-tests-0123456789"
CFG = load_config()
PINNED = CFG["llm"]["model_id"]
GOOD = {"action": "adjust_params", "rationale": "more gain",
        "chain": [{"block_id": "od_ts808", "params": [{"name": "drive", "value": 0.64}]}]}
OPUS = {"inputTokens": 2, "outputTokens": 394, "cacheReadInputTokens": 0, "cacheCreationInputTokens": 5045,
        "thinkingTokens": 189, "costUSD": 0.048}
HAIKU = {"inputTokens": 3700, "outputTokens": 22, "cacheReadInputTokens": 788, "cacheCreationInputTokens": 0,
         "costUSD": 0.0004}


def result(structured=GOOD, subtype="success", is_error=False, status=None, usage=None, stop="tool_use"):
    return ResultMessage(subtype=subtype, duration_ms=4981, duration_api_ms=5502, is_error=is_error, num_turns=2,
                         session_id="s", stop_reason=stop, total_cost_usd=0.0486, structured_output=structured,
                         api_error_status=status, model_usage=usage if usage is not None else {PINNED: OPUS, "claude-haiku-5-5": HAIKU})


def answer(model=PINNED, error=None):
    return AssistantMessage(content=[ToolUseBlock(id="t1", name="StructuredOutput", input={})], model=model, error=error)


class StandIn:
    """Replays one list of messages per call (or raises an exception given instead of a list)."""

    def __init__(self, *calls):
        self.calls, self.prompts, self.options = list(calls), [], []

    def __call__(self, *, prompt, options):
        self.prompts.append(prompt)
        self.options.append(options)
        item = self.calls.pop(0)

        async def gen():
            if isinstance(item, Exception):
                raise item
            for m in item:
                yield m
        return gen()


def client(*calls, sleeps=None):
    fn = StandIn(*calls)
    c = ClaudeSDKLLM(CFG, query_fn=fn, token=TOKEN, sleep=(sleeps.append if sleeps is not None else lambda s: None))
    return c, fn


def test_structured_answer_and_usage():
    c, fn = client([answer(), result()])
    out, u = c.generate("planner", "SYSTEM", "PROMPT", PlannerDecision)
    assert out.action == "adjust_params" and out.chain[0].params[0].value == 0.64
    assert (u.input_tokens, u.output_tokens, u.cache_creation_tokens, u.thinking_tokens) == (5047, 394, 5045, 189)
    assert u.models_used == [PINNED] and u.aux_models == {"claude-haiku-5-5": {"in": 4488, "out": 22}}
    assert (u.client, u.num_turns, u.attempts, u.model_id, u.effort) == ("claude_agent_sdk", 2, 1, PINNED, CFG["llm"]["effort"])
    assert u.sdk_cost_estimate_usd == pytest.approx(0.0486) and u.wall_ms >= 0


def test_options_no_tools_no_settings_token_only_in_child_env():
    c, fn = client([answer(), result()])
    c.generate("planner", "SYSTEM", "PROMPT", PlannerDecision)
    o = fn.options[0]
    assert (o.model, o.effort, o.system_prompt, o.tools, o.setting_sources) == (PINNED, CFG["llm"]["effort"], "SYSTEM", [], [])
    assert o.max_turns == CFG["llm"]["sdk_max_turns"] and o.output_format["type"] == "json_schema"
    assert o.env["CLAUDE_CODE_OAUTH_TOKEN"] == TOKEN and o.env["ANTHROPIC_API_KEY"] == ""
    assert o.env["CLAUDE_CODE_SKIP_PROMPT_HISTORY"] == "1" and o.env["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] == "1"
    assert Path(o.cwd).resolve() != REPO_ROOT.resolve() and not Path(o.cwd).exists()     # temporary, removed after


def test_invalid_output_is_retried_with_the_error_then_fails():
    bad = {"action": "adjust_params"}                                           # missing fields
    c, fn = client([answer(), result(bad)], [answer(), result()])
    out, u = c.generate("planner", "S", "PROMPT", PlannerDecision)
    assert u.attempts == 2 and u.output_tokens == 2 * 394 and "previous answer was invalid" in fn.prompts[1]
    c, _ = client([answer(), result(bad)], [answer(), result(subtype="error_max_structured_output_retries",
                                                                 is_error=True, structured=None)])
    with pytest.raises(LLMOutputError) as e:
        c.generate("planner", "S", "P", PlannerDecision)
    assert e.value.usage.attempts == 2 and e.value.usage.output_tokens == 2 * 394


def test_usage_limit_brief_retry_then_success():
    sleeps = []
    c, fn = client([answer(error="rate_limit"), result(structured=None, is_error=True, subtype="error_during_execution")],
                   [result(structured=None, is_error=True, status=429, subtype="error_during_execution")],
                   [answer(), result()], sleeps=sleeps)
    out, u = c.generate("planner", "S", "P", PlannerDecision)
    assert out.action == "adjust_params" and sleeps == CFG["llm"]["rate_limit_retry_s"][:2] and len(fn.prompts) == 3


def test_usage_limit_persists_raises_usage_limit_error():
    sleeps = []
    limited = [answer(error="rate_limit"), result(structured=None, is_error=True, subtype="error_during_execution")]
    c, fn = client(*[limited] * 4, sleeps=sleeps)
    with pytest.raises(UsageLimitError):
        c.generate("planner", "S", "P", PlannerDecision)
    assert sleeps == CFG["llm"]["rate_limit_retry_s"]


def test_login_failure_stops_at_once():
    sleeps = []
    c, fn = client([answer(error="authentication_failed"), result(structured=None, is_error=True)], sleeps=sleeps)
    with pytest.raises(LLMInfraError) as e:
        c.generate("planner", "S", "P", PlannerDecision)
    assert not isinstance(e.value, UsageLimitError) and sleeps == [] and len(fn.prompts) == 1


def test_answer_from_another_model_is_rejected():
    c, _ = client([answer(model="claude-haiku-5-5"), result()])
    with pytest.raises(LLMInfraError, match="not the pinned"):
        c.generate("planner", "S", "P", PlannerDecision)


def test_process_errors_are_retried_and_the_token_is_redacted():
    err = ProcessError(f"CLI exited, env CLAUDE_CODE_OAUTH_TOKEN={TOKEN}", exit_code=1)
    c, _ = client(*[err] * 4)
    with pytest.raises(LLMInfraError) as e:
        c.generate("planner", "S", "P", PlannerDecision)
    assert TOKEN not in str(e.value) and "[REDACTED]" in str(e.value)


def test_missing_token_and_client_factory(monkeypatch):
    with pytest.raises(LLMInfraError, match="CLAUDE_CODE_OAUTH_TOKEN"):
        ClaudeSDKLLM(CFG, query_fn=StandIn(), token="")
    monkeypatch.setattr(llm_mod, "oauth_token", lambda: TOKEN)
    assert isinstance(make_real_llm({**CFG, "llm": {**CFG["llm"], "client": "claude_agent_sdk"}}), ClaudeSDKLLM)
    monkeypatch.setattr(llm_mod, "AnthropicLLM", lambda cfg: "anthropic client")    # no key needed for this check
    assert make_real_llm({**CFG, "llm": {**CFG["llm"], "client": "anthropic_api"}}) == "anthropic client"


def test_usage_limit_stops_the_batch_cleanly_and_the_token_is_nowhere(tmp_path, monkeypatch, capsys):
    """Runner: a persistent usage limit ends the run as infra_error, stops the batch with a resume message;
    the token appears in no run file and no output."""
    from scripts import run_benchmark
    limited = [answer(error="rate_limit"), result(structured=None, is_error=True, subtype="error_during_execution")]
    fn = StandIn(*[limited] * 4)
    monkeypatch.setattr(llm_mod, "make_real_llm",
                        lambda cfg=None: ClaudeSDKLLM(CFG, query_fn=fn, token=TOKEN, sleep=lambda s: None))
    rc = run_benchmark.main(["--method", "agent", "--llm", "real", "--targets", "G01,G02", "--seeds", "1",
                             "--out", str(tmp_path)], input_fn=lambda _: "yes")
    out = capsys.readouterr().out
    assert rc == 3 and "Usage limit reached after 0 of 2 runs" in out and "Resume later with the same command" in out
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1 and '"infra_error"' in files[0].read_text(encoding="utf-8")
    assert run_benchmark.finished(tmp_path) == set()                       # re-run on resume
    for p in tmp_path.rglob("*"):
        if p.is_file():
            assert TOKEN.encode() not in p.read_bytes(), p
    assert TOKEN not in out
