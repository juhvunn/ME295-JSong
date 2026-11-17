# Plan: Claude Agent SDK client with a Claude Code OAuth token

Status: **approved 2026-11-16** (see the approval record in section 0). Implementation follows section 6.

## Why
The course Enterprise plan has no API keys. The TA approved using a Claude Code OAuth token
(`claude setup-token`, stored by the user in `.env` as `CLAUDE_CODE_OAUTH_TOKEN`). The Agent SDK runs
Claude Code under the hood, so it can use that token. Only the LLM client changes; the LangGraph graph,
Validate, Checker, Router, runner and dashboard stay as they are.

## 0. Facts from the current docs (fetched 2026-11-16)

| Topic | What the docs say | Source |
|---|---|---|
| Auth | SDK docs name `ANTHROPIC_API_KEY`; `CLAUDE_CODE_OAUTH_TOKEN` is documented for the Claude Code CLI ("for CI pipelines and scripts", "can only make model requests", needs a Pro/Max/Ultra/Team/Enterprise plan) but **not explicitly listed for the SDK**. The SDK does not read `.env` itself. | agent-sdk/quickstart, authentication |
| Terms | "OAuth authentication is intended exclusively for purchasers of … subscription plans and is designed to support ordinary use of Claude Code and other native Anthropic applications." "Developers building products or services … including those using the Agent SDK, should use API key authentication." "Advertised usage limits … assume ordinary, individual usage of Claude Code and the Agent SDK." | legal-and-compliance |
| Install | `pip install claude-agent-sdk`; Python 3.10+; the x64 Windows wheel bundles the Claude Code binary (no Node needed). | agent-sdk/quickstart |
| Model, effort | `ClaudeAgentOptions(model=..., effort="low"\|"medium"\|"high"\|"xhigh"\|"max")`; whether `claude-opus-5-5` is accepted by full ID: to verify. | agent-sdk/python |
| One call | `query(prompt=..., options=...)` (new session per call); `system_prompt="..."` (a string **replaces** the default prompt); `max_turns`; `setting_sources=[]` (no user/project settings, no CLAUDE.md); `cwd`; `permission_mode`; `env`. `tools=[]` is not documented; `disallowed_tools` removes named tools. | agent-sdk/python, modifying-system-prompts |
| Structured output | `output_format={"type": "json_schema", "schema": Model.model_json_schema()}` (JSON Schema draft-07); result in `ResultMessage.structured_output` (a dict: we validate it with Pydantic). The SDK re-prompts on mismatch; failure subtype `error_max_structured_output_retries`. It adds its own `StructuredOutput` tool, so the call is not strictly tool-free. | agent-sdk/structured-outputs |
| Usage | `ResultMessage`: `usage`, `model_usage` (per model: input/output/cache tokens, `costUSD`), `total_cost_usd` ("client-side estimates, not authoritative billing"), `num_turns`, `duration_ms`, `stop_reason`, `subtype`, `is_error`, `api_error_status`. | agent-sdk/python, cost-tracking |
| Errors | `AssistantMessage.error`: `rate_limit`, `authentication_failed`, `billing_error`, …; exceptions `CLINotFoundError`, `CLIConnectionError`, `ProcessError`/`ResultError`; `query()` raises after yielding an error result. No documented retry guidance for rate limits. | agent-sdk/python, troubleshooting |
| Transcripts | Written by default to `~/.claude/projects/…` (outside the repo); in Python, setting `CLAUDE_CODE_SKIP_PROMPT_HISTORY` in `env` suppresses them. | agent-sdk/sessions |

**Compliance note.** The docs direct Agent SDK developers to API keys and describe OAuth as intended for
ordinary use of Claude Code. Our use is one student's own research loop on their own Enterprise seat,
with TA approval; we do not offer login to anyone else. The docs do not settle whether this counts as
ordinary use. **Action: keep the TA's approval in writing (citing the legal-and-compliance page) and
record it here before the first real run.** If Anthropic or the course says otherwise, the
`anthropic_api` client (unchanged) is the fallback once a key is available.

**Approval record.** 11/16/2026, in class: "TA recommended using an authentication token (or subagents)
because the course Enterprise plan has no API keys." (A written confirmation describing the Agent SDK
use may follow; if so, it is added here.) Plan approved by the user on 2026-11-16, with the usage-limit
update in section 3; the per-run Planner-call cap (2 × budget = 24) stays as is (it guards against
loops, not cost).

## 1. Design

**New client, old one kept.** `ClaudeSDKLLM` in `pedal_agent/llm.py`, implementing the same
`LLM` protocol (`generate(node, system, prompt, schema) -> (output, LLMUsage)`). `AnthropicLLM` and
`FakeLLM` stay as they are, so their tests are unchanged. `config.yaml` gets `llm.client:
claude_agent_sdk | anthropic_api`; the CLI and `scripts/run_benchmark.py` pick the client from it
(one small factory function).

**One call = one `query()`**, made synchronous with `asyncio.run`:
- `model` and `effort` from `config.yaml` (pinned, as now);
- `system_prompt` = our node prompt (replaces Claude Code's default prompt);
- no tools: `tools=[]` if the smoke test shows it works, else `disallowed_tools` = every built-in tool;
- `setting_sources=[]`, `cwd` = an empty temporary folder (no repo files, no CLAUDE.md),
  `permission_mode="dontAsk"`;
- `max_turns`: the smallest value that lets the `StructuredOutput` tool answer (expected 1 or 2;
  measured in the smoke test);
- `output_format` = JSON schema of `ToneDraft` / `PlannerDecision`;
- `env` = the OAuth token plus `CLAUDE_CODE_SKIP_PROMPT_HISTORY=1` and `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1`.

**Validation and retry.** `structured_output` is validated with our Pydantic models; on failure our
existing bounded retry (`llm.max_retries`) re-asks with the error, exactly as `AnthropicLLM` does.
LLM output is still never executed: only validated numbers and choices reach Build.

**What was actually used.** `LLMUsage` gets optional fields (old records still load):
`model_used` (from `model_usage` keys), `client` (`claude_agent_sdk`), `sdk_version`, `num_turns`,
`duration_ms`, `cache_read_tokens`, `cache_creation_tokens`, `sdk_cost_estimate_usd`. If the model
actually used differs from the pinned `model_id`, the call fails (hard rule: pinned model) and the
difference is recorded.

## 2. Cost becomes "API-equivalent cost"
There is no per-token billing on the plan, so a dollar figure is only a comparison number.
- `RunRecord`: new property `api_equivalent_cost_usd` (tokens × config prices); `cost_usd` stays as an
  alias so old code and tests keep working.
- Summary and dashboard: the column/label becomes **"API-equivalent cost (USD, no per-token billing)"**.
  The SDK's own estimate is recorded per call but not used for results (the docs call it an estimate).
- Token counts from the SDK include Claude Code's own framing, so they are not directly comparable with
  raw Messages API counts; this is stated wherever costs are reported.

## 3. Usage gate and usage limits
The Enterprise allowance is large and, when its maximum is reached, refills within 6 hours (user,
2026-11-16). So pacing stays simple:
- `--llm real` keeps a typed-"yes" gate before a batch, showing: number of runs, expected and
  worst-case LLM calls, expected tokens, API-equivalent cost, and estimated wall time (from the measured
  time per run once we have it).
- No hourly call cap and no fixed gap between calls.
- Usage limit / rate limit (`rate_limit` error or HTTP 429): a **brief retry** (e.g. 3 attempts, 15 s,
  30 s, 60 s). If it persists, the call raises an infrastructure exception: the run ends as `infra_error`
  (re-run on resume, never counted as a method failure, as for the file-save incident), the runner
  **stops the batch cleanly** and prints: "Usage limit reached after N of M runs. The allowance refills
  within about 6 hours; resume later with the same command: <command>". Finished runs are kept; resume
  skips them.
- `authentication_failed` / `billing_error`: stop immediately with a clear message (no retries).

## 4. Secrets
- `.env` stays gitignored (`.gitignore` line 1; checked again before the first commit with `git check-ignore`).
- The token is read with `python-dotenv` and passed **only** in the SDK child process `env`; it is never
  printed, never stored in `RunRecord`, `LLMUsage`, logs or run files. Error texts that go into
  `Step.why` are passed through a redaction function that replaces the token value with `[REDACTED]`.
- Session transcripts are suppressed via `CLAUDE_CODE_SKIP_PROMPT_HISTORY`; any that are still written
  would go to `~/.claude/projects/…`, outside the repo.
- Test: with a fake token value, run the client against a stand-in `query` (including an error path)
  and assert the value appears nowhere in the saved run JSON or captured output.

## 5. Tests (no network, existing tests unchanged)
New `tests/test_llm_sdk.py` with a stand-in for `query()`:
structured output accepted; invalid output retried and then `LLMOutputError` (usage summed);
`error_max_structured_output_retries` handled; rate limit backs off (sleep mocked) and finally
raises an infrastructure error; auth failure stops without retries; model mismatch rejected;
token redaction; usage fields recorded; client factory picks the configured client.
`tests/test_real_run.py` gains an SDK variant, skipped unless `CLAUDE_CODE_OAUTH_TOKEN` is set.

## 6. Order of work (each step: tests, report, your OK)
1. Install `claude-agent-sdk` (version pinned, numpy/scipy held), plus a **smoke script that you run**
   with your token: one Planner call. It shows the model actually used, effort accepted or not,
   whether `tools=[]` and the `max_turns` value work, whether our schema passes the draft-07 check,
   and the measured tokens. Nothing is written to `runs/`.
2. `ClaudeSDKLLM` + factory + `LLMUsage` fields + tests.
3. Cost labels ("API-equivalent"), usage gate, brief retry and clean batch stop on usage limits.
4. One real end-to-end run (CLI, one goal), then one benchmark target; replace the placeholder token
   estimate in `config.yaml` with the measured tokens and record the measured wall time per run;
   then the scale proposal (section 6b).

## 6b. Benchmark scale for the agent methods (proposal after step 4)
The allowance makes larger agent runs possible than the 12-target subset of P3. After the first
measured real run, I will propose a scale **based on measured wall time per run** (SDK calls start a
Claude Code process and may be slow) and measured tokens per run, for example:
- `agent` and `baseline_fixed_topology` (LLM, same budget), both on the same targets;
- **5 or more repeats on B and C targets** (the categories that answer the research question), fewer
  on A, 1–2 on D and hand targets;
- the **full 36-target set** instead of the subset, if the time allows; otherwise the subset first,
  then the rest in later batches (resume makes this safe).
The proposal will give: runs per method, estimated wall time (runs × measured time per run), tokens and
API-equivalent cost, and how many batches/refill windows it would take. The subset view in the summary
stays, so subset and full-set results remain comparable with the random baselines (20 seeds).

### Measured (2026-11-16, two timing runs, agent, seed 1, kept in runs/bench_timing/, not results)
| Run | Outcome | Wall time | Planner calls | Tokens in / out | API-equivalent |
|---|---|---|---|---|---|
| U3 (D) | budget, 12 sims, best 1/2; 6 topology changes, 2 duplicate proposals | 186 s | 13 | 117,423 / 12,858 | $0.73 |
| G25 (C, needs tuning) | budget, 12 sims, best 3/4 (THD 9.2 % < 24.6 %); 6 topology changes | 140 s | 11 | 84,326 / 9,526 | $0.53 |

- Per call: median 11–14 s, max 21 s. The prompt we send grows only from ~5.8k to ~7.4k characters over
  a run; input tokens alternate between ~5k (2 SDK turns) and ~11–12k (3 turns, about half the calls).
- **Planning numbers for a run that uses the full budget: about 2.7 min, ~100k tokens in, ~11k out,
  ~$0.63 API-equivalent.** Runs that succeed early are shorter, so these are upper estimates.
- Observation (analysis only, from the hidden solution): G25 needs `od_ts808 → dist_distplus`; the agent
  tried two-block chains twice, both times in the order `dist_distplus → od_ts808`.

### Proposal
Both LLM methods (`agent`, `baseline_fixed_topology`) on the same targets and repeats; `seed` is only a
repeat number for them (LLM calls are not seeded).

| Option | Repeats per target | Runs per method | Runs total | Wall time (upper) | Tokens in / out | API-equivalent |
|---|---|---|---|---|---|---|
| **S: subset (12 targets)** | A 3, B 5, C 5, D 2, hand 3 (2·3 + 4·5 + 4·5 + 1·2 + 1·3) | 51 | 102 | ≈ 4.6 h | ≈ 10 M / 1.1 M | ≈ $64 |
| **F: full set (36 targets)** | A 3, B 5, C 5, D 2, hand 3 (7·3 + 9·5 + 10·5 + 4·2 + 6·3) | 142 | 284 | ≈ 12.8 h | ≈ 29 M / 3.2 M | ≈ $179 |

**Decision (user, 2026-11-16): S, then F.** Command per method (`agent`, `baseline_fixed_topology`):
`python -m scripts.run_benchmark --set v1 --method <m> --llm real --targets subset --repeats A=3,B=5,C=5,D=2,hand=3`
(F: the same with `--targets all`; finished runs are skipped).

**Freeze for the whole S+F evaluation.** Each run records the git commit it ran on (`code_commit`,
`code_dirty`), the summary lists the commits per method, and the runner refuses a real-LLM batch when
tracked files differ from the commit. Between the S and F batches nothing that affects the agent changes:
prompts, agent code, config affecting the agent, the Checker, blocks, models and benchmarks.
**Not fixed: the block-order weakness seen on G25** (the agent tried `dist_distplus → od_ts808` but not
the solution's `od_ts808 → dist_distplus`): fixing it now would tune the agent to the test set. It is an
observation to check across the S results (the summary's block-order table counts runs that tried both
orders of a pair, and for C targets whether the solution's order or only the reversed one was tried).
Agent improvements go into a later version, evaluated on a new benchmark version.

**Recommendation: S first** (one evening), check the results and any agent problems (e.g. block
order), then extend to **F** in two further batches of ~4 h (the 182 extra runs), resumable after a
usage-limit stop. Statistical note: with 5 repeats, the subset gives 20 runs per method in B and in C
(95 % interval about ±20 points at 50 %); the full set gives 45–50 (about ±14 points). The random
baselines already have 20 seeds on all targets, and the summary's subset view compares all methods on
exactly the same targets.

## 7. Fallback: Claude Code subagents (and why we prefer the SDK)
Alternative: run the Planner as a Claude Code subagent (or a `claude -p` headless call per step),
driven from a Claude Code session.
- **Pros:** clearly "ordinary use of Claude Code"; no SDK dependency.
- **Cons:** the graph would no longer run unattended from Python: each Planner step would need an
  interactive session or a shell-out per call, making equal-budget, many-seed benchmark runs slow and
  hard to reproduce; token usage, retries, validation and the human interrupts would have to be rebuilt
  around a chat transcript; the dashboard's live-run actions could not call it.
- The SDK keeps the existing contract (`generate()` returns validated Pydantic output + usage), so the
  graph, the benchmark protocol and all tests stay exactly as they are. Subagents remain the fallback if
  SDK use with the OAuth token turns out not to be acceptable.

## Risks
- `CLAUDE_CODE_OAUTH_TOKEN` with the SDK is not explicitly documented: step 1 verifies it.
- Each call starts a Claude Code subprocess: slower than a raw API call (measured in step 1).
- Plan usage limits may interrupt long batches: the runner stops cleanly and resumes after the refill.
- Model or effort may not be available on the plan: step 1 shows what is actually used.
