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
