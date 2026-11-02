# Project: Multi-Agent Guitar Amp Circuit Design with SPICE Feedback
Course: AM/ME/CE 295 (Caltech, Fall 2026). Solo project. Status: early implementation (as of Nov 1, 2026).

## Goal
Multi-agent system that turns natural-language tone goals (e.g. "warm crunch") into measurable specs,
proposes circuits from a constrained block library, and revises them using ngspice feedback.
A human approves the final design before export.
Scope: preamp/overdrive signal path only. Out of scope: power amp, speaker/cabinet, listening tests, real-time audio, physical build.

## Research question
Under equal simulation budgets, does an agent loop that can change topology (not only component values)
reach more specs than a fixed-topology parameter search and a single LLM?

## Architecture
- LLM agents: Planner (coordinates, revises), Tone Analyst (tone -> schema-validated spec), Library Searcher (picks blocks from approved catalog only)
- Deterministic code (NO LLM): validate_circuit, build_netlist, simulate (sandboxed ngspice), evaluate (Checker), memory
- Blocks v1: diode clipper, op-amp gain stage, RC tone control
- Metrics: gain, AC frequency response, THD + harmonic ratios (steady-state transient)
- Tools (plain Python): search_blocks, validate_circuit, build_netlist, simulate, evaluate, get_history, export_design
- Session memory: JSONL, one record per candidate {id, parent_id, blocks, values, protocol_version, status, metrics, violations, rationale, change_type: "topology"|"values"}

## Baselines (all use the same evaluate() and protocol, equal simulation budget)
1. Single LLM, one candidate
2. Single LLM with the same tools (no role split)
3. Fixed-topology parameter search (grid/random)

## Hard rules
- Model ID is read ONLY from config.yaml (pinned). Never hardcode.
- Never commit API keys. Use .env (gitignored). Never print keys.
- LLM-generated text is never executed directly. Netlists come only from trusted templates in build_netlist.
- Filter dangerous SPICE directives (.shell, .system, .include, shell inside .control). Always use a timeout.
- All LLM outputs are validated with Pydantic; on failure, return the error and retry (bounded).
- Checker feedback to the Planner is structured numbers (target, got, error), not prose.
- Prefer deterministic checkers over LLM checkers.
- Every Planner revision logs whether it changed topology or only values.
- Any consequential action (export, git push, deleting files) requires my approval.
- Verify the Checker on known circuits before trusting results: non-inverting op-amp gain (1+Rf/Rg), RC low-pass -3 dB at 1/(2*pi*R*C), pure sine THD ~ 0.

## Environment
Windows, VS Code, conda env [ENV_NAME — TODO: no conda found on this machine], ngspice 41, Python [VERSION — TODO: no Python found on this machine]. Repo: local only (D:\Users\jsong3\ME295-JSong, no remote).
Note: `logs/` holds ngspice run logs; `runs/<id>/` holds netlists and simulation output (gitignored).

## Workflow for you (Claude Code)
- Work in small steps; run tests after each change and show me the results.
- Append every Claude contribution (date, what, files) to LOG.md for my AI Use Declaration.
- Do not invent results. If something fails, report the real error.

## Target layout
config.yaml, blocks/block_library.yaml, protocol/protocol_v1.yaml, targets/targets_v1.yaml,
src/tools/{validate,build,simulate,evaluate}.py, src/agents/, src/memory.py, src/baselines/, tests/, runs/ (gitignored), README.md, LOG.md
