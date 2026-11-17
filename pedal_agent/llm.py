"""LLM clients for the Tone Analyst and Planner nodes.

Every client returns (validated Pydantic output, LLMUsage). AnthropicLLM calls
Claude with structured outputs; FakeLLM replays a fixed script with no API
calls, so graph tests are free and repeatable.
"""
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from pedal_agent.config import load_config
from pedal_agent.schemas import LLMUsage, MetricTarget, PlannerDecision, ToneDraft

T = TypeVar("T", bound=BaseModel)


class LLMOutputError(RuntimeError):
    def __init__(self, message: str, usage: LLMUsage | None = None):
        super().__init__(message)
        self.usage = usage  # tokens spent on the failed attempts, for cost accounting


class LLM(Protocol):
    model_id: str
    effort: str

    def generate(self, node: str, system: str, prompt: str, schema: type[T]) -> tuple[T, LLMUsage]: ...


class AnthropicLLM:
    """Claude via client.messages.parse(output_format=schema). Model and effort come only
    from config.yaml. No temperature (not settable) and no forced tool use (unsupported)."""

    def __init__(self, config: dict | None = None, client=None):
        cfg = (config or load_config())["llm"]
        self.model_id, self.effort = cfg["model_id"], cfg["effort"]
        self.max_tokens, self.attempts = cfg["max_tokens"], cfg["max_retries"]
        if client is None:
            import anthropic
            from dotenv import load_dotenv

            load_dotenv()  # ANTHROPIC_API_KEY from the environment or the gitignored .env
            client = anthropic.Anthropic()
        self.client = client

    def generate(self, node, system, prompt, schema):
        content, error = prompt, None
        tokens_in = tokens_out = 0
        for attempt in range(1, self.attempts + 1):
            usage = None
            try:
                response = self.client.messages.parse(
                    model=self.model_id, max_tokens=self.max_tokens, system=system,
                    messages=[{"role": "user", "content": content}],
                    output_format=schema, output_config={"effort": self.effort})
                usage = response.usage
                parsed = response.parsed_output
                if response.stop_reason == "refusal":
                    tokens_in, tokens_out = tokens_in + usage.input_tokens, tokens_out + usage.output_tokens
                    raise LLMOutputError(f"{node}: model refused ({response.stop_details})",
                                         self._usage(node, tokens_in, tokens_out, attempt))
                error = None if parsed is not None else f"no parsed output (stop_reason={response.stop_reason})"
            except ValidationError as e:
                parsed, error = None, str(e)
            if usage is not None:
                tokens_in, tokens_out = tokens_in + usage.input_tokens, tokens_out + usage.output_tokens
            if error is None:
                return parsed, self._usage(node, tokens_in, tokens_out, attempt)
            content = f"{prompt}\n\nYour previous answer was invalid: {error}\nReturn a corrected answer."
        raise LLMOutputError(f"{node}: no valid {schema.__name__} after {self.attempts} attempts: {error}",
                             self._usage(node, tokens_in, tokens_out, self.attempts))

    def _usage(self, node, tokens_in, tokens_out, attempts) -> LLMUsage:
        return LLMUsage(node=node, model_id=self.model_id, effort=self.effort,
                        input_tokens=tokens_in, output_tokens=tokens_out, attempts=attempts)


class LLMInfraError(RuntimeError):
    """Failure outside the method (login, usage limit, CLI/process trouble, wrong model): not caught by
    the graph, so the run ends as infra_error (re-run on resume, never counted as a method failure)."""


class UsageLimitError(LLMInfraError):
    """Plan usage limit / rate limit still hit after the brief retries: the batch should stop and resume later."""


def redact(text, secret: str | None) -> str:
    return str(text).replace(secret, "[REDACTED]") if secret else str(text)


def oauth_token() -> str:
    """CLAUDE_CODE_OAUTH_TOKEN from the environment or the gitignored .env (never printed or stored)."""
    import os

    from dotenv import dotenv_values

    from pedal_agent.config import REPO_ROOT
    return (os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
            or dotenv_values(REPO_ROOT / ".env").get("CLAUDE_CODE_OAUTH_TOKEN") or "").strip()


class ClaudeSDKLLM:
    """Claude via the Claude Agent SDK, authenticated with a Claude Code OAuth token
    (docs/agent_sdk_plan.md). One query() per attempt: our system prompt replaces Claude Code's, no tools
    (only the SDK's StructuredOutput tool), no settings or CLAUDE.md, an empty temporary cwd, transcripts
    off. Model and effort come only from config.yaml; the model that wrote the answer must be the pinned
    one. Invalid output is retried like AnthropicLLM (llm.max_retries); usage limits are retried briefly
    (llm.rate_limit_retry_s) and then raise UsageLimitError."""
    client = "claude_agent_sdk"
    AUTH_ERRORS = {"authentication_failed", "billing_error"}

    def __init__(self, config: dict | None = None, query_fn=None, token: str | None = None, sleep=None):
        import time
        cfg = (config or load_config())["llm"]
        self.model_id, self.effort, self.attempts = cfg["model_id"], cfg["effort"], cfg["max_retries"]
        self.max_turns = cfg.get("sdk_max_turns", 3)
        self.retry_s = list(cfg.get("rate_limit_retry_s", [15, 30, 60]))
        self.token = oauth_token() if token is None else token
        if not self.token:
            raise LLMInfraError("CLAUDE_CODE_OAUTH_TOKEN is not set (run `claude setup-token`, put it in .env)")
        if query_fn is None:
            from claude_agent_sdk import query as query_fn
        self.query_fn, self.sleep = query_fn, sleep or time.sleep
        try:
            from importlib.metadata import version
            self.sdk_version = version("claude-agent-sdk")
        except Exception:
            self.sdk_version = None

    def _options(self, system: str, schema, cwd: str):
        from claude_agent_sdk import ClaudeAgentOptions
        return ClaudeAgentOptions(
            model=self.model_id, effort=self.effort, system_prompt=system, tools=[], setting_sources=[],
            cwd=cwd, permission_mode="dontAsk", max_turns=self.max_turns,
            output_format={"type": "json_schema", "schema": schema.model_json_schema()},
            env={"CLAUDE_CODE_OAUTH_TOKEN": self.token, "ANTHROPIC_API_KEY": "",
                 "CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1", "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1",
                 "DISABLE_NON_ESSENTIAL_MODEL_CALLS": "1"})

    def _once(self, system: str, prompt: str, schema) -> dict:
        """One query(): what happened, as plain data. Never raises for SDK-reported errors."""
        import asyncio
        import tempfile
        import time

        from claude_agent_sdk import AssistantMessage, RateLimitEvent, ResultMessage

        got = {"models": [], "errors": [], "rate_limited": False, "result": None, "exception": None}

        async def run(cwd):
            async for msg in self.query_fn(prompt=prompt, options=self._options(system, schema, cwd)):
                if isinstance(msg, AssistantMessage):
                    got["models"].append(msg.model)
                    if msg.error:
                        got["errors"].append(msg.error)
                elif isinstance(msg, RateLimitEvent) and msg.rate_limit_info.status == "rejected":
                    got["rate_limited"] = True
                elif isinstance(msg, ResultMessage):
                    got["result"] = msg

        t0 = time.time()
        try:
            with tempfile.TemporaryDirectory() as cwd:
                asyncio.run(run(cwd))
        except Exception as e:          # CLI/process errors; query() also raises after an error result
            got["exception"] = f"{type(e).__name__}: {redact(e, self.token)}"
        got["wall_ms"] = int((time.time() - t0) * 1000)
        r = got["result"]
        got["rate_limited"] |= "rate_limit" in got["errors"] or (r is not None and r.api_error_status == 429)
        return got

    def _call(self, node: str, system: str, prompt: str, schema) -> dict:
        """_once() with brief retries on usage limits / process failures; raises LLMInfraError."""
        for i, wait in enumerate([0] + self.retry_s):
            if wait:
                self.sleep(wait)
            got = self._once(system, prompt, schema)
            if self.AUTH_ERRORS & set(got["errors"]) or (got["result"] is not None and
                                                         got["result"].api_error_status in (401, 403)):
                raise LLMInfraError(f"{node}: login/billing refused ({', '.join(got['errors']) or 'HTTP 401/403'}); "
                                    "check CLAUDE_CODE_OAUTH_TOKEN")
            transient = got["rate_limited"] or (got["result"] is None and got["exception"])
            if not transient:
                return got
        if got["rate_limited"]:
            raise UsageLimitError(f"{node}: usage limit still reached after {len(self.retry_s)} retries")
        raise LLMInfraError(f"{node}: Claude Agent SDK call failed after {len(self.retry_s)} retries: {got['exception']}")

    def generate(self, node, system, prompt, schema):
        content, error = prompt, None
        tot = {"in": 0, "out": 0, "cw": 0, "cr": 0, "think": 0, "turns": 0, "wall": 0, "cost": 0.0}
        aux: dict[str, dict] = {}
        used: set[str] = set()
        for attempt in range(1, self.attempts + 1):
            got = self._call(node, system, content, schema)
            r = got["result"]
            used |= set(got["models"])
            tot["wall"] += got["wall_ms"]
            if r is not None:
                tot["turns"] += r.num_turns or 0
                tot["cost"] += r.total_cost_usd or 0.0
                for model, u in (r.model_usage or {}).items():
                    u = u if isinstance(u, dict) else vars(u)
                    if model == self.model_id:
                        tot["in"] += u.get("inputTokens", 0) + u.get("cacheCreationInputTokens", 0) + u.get("cacheReadInputTokens", 0)
                        tot["cw"] += u.get("cacheCreationInputTokens", 0)
                        tot["cr"] += u.get("cacheReadInputTokens", 0)
                        tot["out"] += u.get("outputTokens", 0)
                        tot["think"] += u.get("thinkingTokens", 0)
                    else:
                        a = aux.setdefault(model, {"in": 0, "out": 0})
                        a["in"] += u.get("inputTokens", 0) + u.get("cacheCreationInputTokens", 0) + u.get("cacheReadInputTokens", 0)
                        a["out"] += u.get("outputTokens", 0)
            usage = self._usage(node, tot, attempt, sorted(used), aux)
            wrong = sorted(m for m in got["models"] if m != self.model_id)
            if wrong:
                raise LLMInfraError(f"{node}: answer written by {wrong}, not the pinned {self.model_id}")
            if r is not None and r.stop_reason == "refusal":
                raise LLMOutputError(f"{node}: model refused", usage)
            if r is None or r.is_error or r.subtype != "success" or r.structured_output is None:
                error = (f"no structured output (subtype={getattr(r, 'subtype', None)}, "
                         f"errors={[redact(e, self.token) for e in (getattr(r, 'errors', None) or [])]})")
                parsed = None
            else:
                try:
                    parsed, error = schema.model_validate(r.structured_output), None
                except ValidationError as e:
                    parsed, error = None, str(e)
            if error is None:
                return parsed, usage
            content = f"{prompt}\n\nYour previous answer was invalid: {error}\nReturn a corrected answer."
        raise LLMOutputError(f"{node}: no valid {schema.__name__} after {self.attempts} attempts: {error}", usage)

    def _usage(self, node, tot, attempts, used, aux) -> LLMUsage:
        return LLMUsage(node=node, model_id=self.model_id, effort=self.effort, input_tokens=tot["in"],
                        output_tokens=tot["out"], attempts=attempts, client=self.client, models_used=used or None,
                        cache_creation_tokens=tot["cw"], cache_read_tokens=tot["cr"], thinking_tokens=tot["think"],
                        aux_models=aux or None, num_turns=tot["turns"], wall_ms=tot["wall"],
                        sdk_cost_estimate_usd=round(tot["cost"], 6), sdk_version=self.sdk_version)


def make_real_llm(config: dict | None = None):
    """The real LLM client chosen in config.yaml llm.client (claude_agent_sdk | anthropic_api)."""
    cfg = config or load_config()
    if cfg["llm"].get("client", "anthropic_api") == "claude_agent_sdk":
        return ClaudeSDKLLM(cfg)
    return AnthropicLLM(cfg)


class FakeLLM:
    """Replays script[node] in order; raises LLMOutputError when a node's script runs out."""
    model_id = "fake"
    effort = "none"

    def __init__(self, script: dict[str, list] | None = None):
        script = script if script is not None else default_fake_script()
        self.script = {node: list(items) for node, items in script.items()}
        self.calls: list[tuple[str, str]] = []   # (node, prompt) for test introspection

    def generate(self, node, system, prompt, schema):
        self.calls.append((node, prompt))
        queue = self.script.get(node, [])
        if not queue:
            raise LLMOutputError(f"fake script for {node!r} is exhausted")
        item = queue.pop(0)
        out = item if isinstance(item, schema) else schema.model_validate(item)
        return out, LLMUsage(node=node, model_id=self.model_id, effort=self.effort,
                             input_tokens=0, output_tokens=0)


def _decision(action, chain, why):
    return PlannerDecision.model_validate({
        "action": action, "rationale": why,
        "chain": [{"block_id": b, "params": [{"name": k, "value": v} for k, v in p.items()]} for b, p in chain],
    })


def default_fake_script() -> dict[str, list]:
    """Warm mid-forward overdrive. Exercises swap, invalid, duplicate, adjust, all_pass."""
    tone = ToneDraft(rationale="Fixed fake spec: moderate gain, light breakup, mid hump, symmetric.", targets=[
        MetricTarget(name="gain_1k_db", lo=15, hi=22, unit="dB", label="Gain at 1 kHz"),
        MetricTarget(name="thd_pct", lo=2, hi=10, unit="%", label="THD (300 mV)"),
        MetricTarget(name="ac_peak_hz", lo=600, hi=1000, unit="Hz", label="Mid peak"),
        MetricTarget(name="even_odd", hi=0.5, label="Even / odd harmonics"),
    ])
    planner = [
        _decision("initial_chain", [("dist_distplus", {})], "Start from a simple distortion."),
        _decision("swap_block", [("od_ts808", {"drive": 0.5})], "Peak too high; the TS-808 has a mid hump."),
        _decision("adjust_params", [("od_ts808", {"drive": 1.5})], "More gain."),            # invalid: > 1
        _decision("adjust_params", [("od_ts808", {"drive": 0.5})], "Retry the TS-808."),     # duplicate
        _decision("adjust_params", [("od_ts808", {"drive": 0.7})], "Gain below 15 dB; raise drive."),
    ]
    return {"tone_analyst": [tone], "planner": planner}
