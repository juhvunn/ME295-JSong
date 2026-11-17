"""One-call smoke test of the Claude Agent SDK with a Claude Code OAuth token (docs/agent_sdk_plan.md, step 1).

Sends ONE Planner request, the real Planner prompt built from the illustrative example run (no
simulation), and reports what the SDK actually did:
  auth works, model actually used, effort accepted, tools available in the session (should be none
  besides the SDK's StructuredOutput tool), turns used, whether the answer validates as a PlannerDecision,
  tokens, time, and the SDK's own cost estimate.
Writes results/sdk_smoke.json (gitignored). Writes nothing to runs/. The token is never printed or saved.

Setup (once): run `claude setup-token` and put the token in .env as CLAUDE_CODE_OAUTH_TOKEN=...
Usage: python -m scripts.sdk_smoke
"""
import asyncio
import json
import os
import sys
import tempfile
import time
from importlib.metadata import version

from dotenv import dotenv_values

from pedal_agent.config import REPO_ROOT, load_config
from pedal_agent.prompts import planner_prompts
from pedal_agent.schemas import PlannerDecision, RunRecord

OUT = REPO_ROOT / "results" / "sdk_smoke.json"


def redact(text, secret):
    return str(text).replace(secret, "[REDACTED]") if secret else str(text)


async def one_call(system, prompt, cfg, token, cwd):
    from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ResultMessage, SystemMessage,
                                  ToolUseBlock, query)
    options = ClaudeAgentOptions(
        model=cfg["llm"]["model_id"], effort=cfg["llm"]["effort"],
        system_prompt=system, tools=[], setting_sources=[], cwd=cwd, permission_mode="dontAsk",
        max_turns=3,                                   # measured: how many turns the StructuredOutput answer needs
        output_format={"type": "json_schema", "schema": PlannerDecision.model_json_schema()},
        env={"CLAUDE_CODE_OAUTH_TOKEN": token, "ANTHROPIC_API_KEY": "",     # use the OAuth token, not a key
             "CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1", "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1"})
    seen = {"session_tools": None, "session_model": None, "assistant_models": [], "tool_uses": [],
            "assistant_errors": [], "result": None}
    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, SystemMessage) and msg.subtype == "init":
            seen["session_tools"] = msg.data.get("tools")
            seen["session_model"] = msg.data.get("model")
        elif isinstance(msg, AssistantMessage):
            seen["assistant_models"].append(msg.model)
            seen["tool_uses"] += [b.name for b in msg.content if isinstance(b, ToolUseBlock)]
            if msg.error:
                seen["assistant_errors"].append(msg.error)
        elif isinstance(msg, ResultMessage):
            seen["result"] = msg
    return seen


def main() -> int:
    cfg = load_config()
    token = (os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or dotenv_values(REPO_ROOT / ".env").get("CLAUDE_CODE_OAUTH_TOKEN") or "").strip()
    if not token:
        print("CLAUDE_CODE_OAUTH_TOKEN is not set: run `claude setup-token` and put the token in .env "
              "as CLAUDE_CODE_OAUTH_TOKEN=... (it is never printed).")
        return 2
    if os.environ.get("ANTHROPIC_API_KEY"):
        print("Note: ANTHROPIC_API_KEY is set in your shell; the smoke test blanks it for the SDK call "
              "so that the OAuth token is used.")
    run = RunRecord.model_validate_json((REPO_ROOT / "runs" / "example-jazz-christmas.json").read_text(encoding="utf-8"))
    system, prompt = planner_prompts(run)
    print(f"Sending one Planner call: model {cfg['llm']['model_id']}, effort {cfg['llm']['effort']}, "
          f"prompt {len(system) + len(prompt)} characters …")

    report = {"sdk_version": version("claude-agent-sdk"), "requested_model": cfg["llm"]["model_id"],
              "requested_effort": cfg["llm"]["effort"]}
    t0 = time.time()
    try:
        with tempfile.TemporaryDirectory() as cwd:      # empty folder: no repo files, no CLAUDE.md
            seen = asyncio.run(one_call(system, prompt, cfg, token, cwd))
    except Exception as e:                              # report the real error, without the token
        report.update(ok=False, error=f"{type(e).__name__}: {redact(e, token)}", wall_s=round(time.time() - t0, 1))
        print("FAILED:", report["error"])
        return finish(report, 1)
    report["wall_s"] = round(time.time() - t0, 1)
    r = seen["result"]
    report.update(session_model=seen["session_model"], session_tools=seen["session_tools"],
                  assistant_models=sorted(set(seen["assistant_models"])), tool_uses=seen["tool_uses"],
                  assistant_errors=seen["assistant_errors"])
    if r is None:
        report.update(ok=False, error="no ResultMessage received")
        return finish(report, 1)
    report.update(subtype=r.subtype, is_error=r.is_error, stop_reason=r.stop_reason, num_turns=r.num_turns,
                  duration_ms=r.duration_ms, duration_api_ms=r.duration_api_ms, api_error_status=r.api_error_status,
                  usage=r.usage, model_usage={k: (v if isinstance(v, dict) else vars(v)) for k, v in (r.model_usage or {}).items()},
                  sdk_cost_estimate_usd=r.total_cost_usd,
                  errors=[redact(e, token) for e in (r.errors or [])])
    try:
        decision = PlannerDecision.model_validate(r.structured_output)
        report.update(valid_planner_decision=True, action=decision.action,
                      chain=[(b.block_id, {p.name: p.value for p in b.params}) for b in decision.chain])
    except Exception as e:
        report.update(valid_planner_decision=False, validation_error=redact(e, token)[:500])
    report["ok"] = bool(r.subtype == "success" and not r.is_error and report["valid_planner_decision"])
    used = list(report["model_usage"]) or report["assistant_models"]
    report["pinned_model_used"] = cfg["llm"]["model_id"] in used
    return finish(report, 0 if report["ok"] else 1)


def finish(report: dict, code: int) -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    keys = ("ok", "error", "subtype", "pinned_model_used", "session_model", "assistant_models", "session_tools",
            "tool_uses", "num_turns", "valid_planner_decision", "action", "chain", "wall_s", "duration_api_ms",
            "usage", "sdk_cost_estimate_usd", "assistant_errors", "errors")
    for k in keys:
        if k in report:
            print(f"{k:24} {report[k]}")
    print(f"\nFull report: {OUT} (no token inside). Send me 'done' and I will read it.")
    return code


if __name__ == "__main__":
    sys.exit(main())
