"""Structured LLM calls: every response is parsed into a Pydantic model.

The model ID comes only from config.yaml. On a validation failure the error is
sent back to the model and the call is retried, up to llm.max_retries times.
"""
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from src.config import load_config

T = TypeVar("T", bound=BaseModel)


class LLMOutputError(RuntimeError):
    pass


class StructuredLLM(Protocol):
    def generate(self, system: str, prompt: str, schema: type[T]) -> T: ...


class AnthropicLLM:
    def __init__(self, config: dict | None = None, client=None):
        cfg = (config or load_config())["llm"]
        if not cfg.get("model_id") or "PLACEHOLDER" in cfg["model_id"]:
            raise ValueError("pin llm.model_id in config.yaml before running agents")
        self.model_id = cfg["model_id"]
        self.max_retries = cfg["max_retries"]
        self.max_tokens = cfg["max_tokens"]
        self.effort = cfg["effort"]
        if client is None:
            import anthropic
            from dotenv import load_dotenv

            load_dotenv()  # ANTHROPIC_API_KEY from the gitignored .env
            client = anthropic.Anthropic()
        self.client = client

    def generate(self, system: str, prompt: str, schema: type[T]) -> T:
        content, last_error = prompt, None
        for _ in range(self.max_retries):
            try:
                response = self.client.messages.parse(
                    model=self.model_id,
                    max_tokens=self.max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": content}],
                    output_format=schema,
                    output_config={"effort": self.effort},
                )
            except ValidationError as e:
                last_error = str(e)
            else:
                if response.stop_reason == "refusal":
                    raise LLMOutputError(f"model refused: {response.stop_details}")
                if response.parsed_output is not None:
                    return response.parsed_output
                last_error = f"no parsed output (stop_reason={response.stop_reason})"
            content = f"{prompt}\n\nYour previous answer was invalid: {last_error}\nReturn a corrected answer."
        raise LLMOutputError(f"no valid {schema.__name__} after {self.max_retries} attempts: {last_error}")
