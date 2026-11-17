"""Run one method over a benchmark set (docs/phase3_plan.md, step 4).

Every run goes through the real graph (new_benchmark_run -> Agent: Validate, Checker, Router) and is
saved as a normal RunRecord JSON in --out (default runs/bench/<set>/<method>/), so the dashboard can
open it. Planner seed k is the same for every target. Finished runs (same target and seed) are
skipped, so an interrupted batch can be resumed by running the same command again.

No peeking: the hidden solutions file is read ONLY by read_solutions(), and only for
random_fixed_topology_oracle (its chain). The oracle is not run on D or hand targets.
--llm real (agent methods) prints an estimated cost and asks for "yes" before any API call.

Usage: python -m scripts.run_benchmark --set v1 --method random_catalog --seeds 5 [--targets all|subset|G01,H2]
"""
import argparse
import json
import sys
import time
from pathlib import Path

import yaml

from pedal_agent.baselines.planners import RandomCatalogPlanner, RandomFixedTopologyPlanner
from pedal_agent.config import REPO_ROOT, load_config
from pedal_agent.graph import Agent, RunStore, new_benchmark_run
from pedal_agent.llm import FakeLLM, _decision
from pedal_agent.schemas import BenchmarkRef, BlockInstance, MetricTarget, TargetSpec

B = REPO_ROOT / "benchmarks"
START = ["od_ts808"]
RANDOM_METHODS = ("random_catalog", "random_fixed_topology", "random_fixed_topology_oracle")
AGENT_METHODS = ("agent", "baseline_fixed_topology")
SECONDS_PER_SIM = 0.4


def load_set(version: str) -> list[dict]:
    return yaml.safe_load((B / f"{version}.yaml").read_text(encoding="utf-8"))["targets"]


def read_solutions(version: str) -> dict:
    """The ONLY reader of the hidden solutions (oracle chains)."""
    return yaml.safe_load((B / f"{version}_solutions.yaml").read_text(encoding="utf-8"))


def select_targets(targets: list[dict], which: str, version: str) -> list[dict]:
    if which == "all":
        return targets
    if which == "subset":
        ids = yaml.safe_load((B / f"{version}_subset.yaml").read_text(encoding="utf-8"))["targets"]
    else:
        ids = which.split(",")
    by_id = {t["id"]: t for t in targets}
    missing = [i for i in ids if i not in by_id]
    if missing:
        raise SystemExit(f"unknown target ids: {missing}")
    return [by_id[i] for i in ids]


def finished(out_dir: Path) -> set[tuple[str, int]]:
    done = set()
    for p in out_dir.glob("*.json"):
        r = json.loads(p.read_text(encoding="utf-8"))
        # infra_error runs (exceptions outside the method) are re-run; every other stop reason is an outcome
        if r.get("stop_reason") and r["stop_reason"] != "infra_error" and r.get("benchmark"):
            done.add((r["benchmark"]["target_id"], r["seed"]))
    return done


def fake_llm() -> FakeLLM:
    """Plumbing only: a scripted planner that turns the od_ts808 drive knob (valid in both agent modes)."""
    drives = [0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9]
    script = [_decision("adjust_params", [("od_ts808", {"drive": drives[i % len(drives)]})], f"fake drive step {i}")
              for i in range(48)]
    return FakeLLM({"planner": script})


def cost_estimate(n_runs: int, cfg: dict) -> tuple[float, float]:
    """(expected, worst case) USD: one planner call per planner sim, or the planner-call cap."""
    llm, b, run = cfg["llm"], cfg["benchmark"], cfg["run"]
    per_call = (b["est_input_tokens_per_call"] * llm["price_in_per_mtok"] +
                b["est_output_tokens_per_call"] * llm["price_out_per_mtok"]) / 1e6
    return (n_runs * (run["sim_budget"] - 1) * per_call,
            n_runs * run["max_planner_calls_per_sim"] * run["sim_budget"] * per_call)


def confirm_real(n_runs: int, cfg: dict, input_fn=input, out=print) -> bool:
    """Usage gate: what a batch will use, then a typed "yes"."""
    exp, worst = cost_estimate(n_runs, cfg)
    b, run = cfg["benchmark"], cfg["run"]
    calls, calls_max = n_runs * (run["sim_budget"] - 1), n_runs * run["max_planner_calls_per_sim"] * run["sim_budget"]
    hours = (calls * b.get("est_seconds_per_call", 9) + n_runs * run["sim_budget"] * SECONDS_PER_SIM) / 3600
    out(f"REAL LLM RUN: {n_runs} runs with {cfg['llm']['model_id']} (effort {cfg['llm']['effort']}, "
        f"client {cfg['llm'].get('client', 'anthropic_api')}).")
    out(f"Planner calls: about {calls} expected, at most {calls_max}; tokens about "
        f"{calls * b['est_input_tokens_per_call']:,} in / {calls * b['est_output_tokens_per_call']:,} out.")
    out(f"Estimated cost (API-equivalent, no per-token billing): about ${exp:.2f} expected, ${worst:.2f} worst case. "
        f"Estimated wall time: about {hours:.1f} h. Plan usage limits apply; if hit, the batch stops and can be resumed.")
    return input_fn('Type "yes" to start: ').strip().lower() == "yes"


def planner_for(method: str, seed: int, chain: list[str], llm):
    if method == "random_catalog":
        return RandomCatalogPlanner(seed, START)
    if method in ("random_fixed_topology", "random_fixed_topology_oracle"):
        return RandomFixedTopologyPlanner(seed, chain)
    return llm


def code_version() -> tuple[str, bool]:
    """(git commit, dirty): dirty = tracked files differ from that commit (untracked files ignored)."""
    import subprocess
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=REPO_ROOT,
                                    capture_output=True, text=True).stdout.strip())
    except OSError:
        return "unknown", True
    return commit or "unknown", dirty


def run_one(version: str, t: dict, method: str, seed: int, store: RunStore, llm=None, oracle_chain=None,
            code: tuple[str, bool] | None = None):
    chain = list(oracle_chain) if method == "random_fixed_topology_oracle" else START
    planner = planner_for(method, seed, chain, llm)
    agent = Agent(planner, store)
    try:
        ref = BenchmarkRef(set=version, target_id=t["id"], category=t["category"],
                           start_chain=[BlockInstance(block_id=b) for b in chain])
        spec = TargetSpec(goal_text=t["label"], targets=[MetricTarget(**x) for x in t["targets"]])
        run = new_benchmark_run(spec, ref, planner, mode=method, seed=seed)
        if code:
            run.code_commit, run.code_dirty = code
        agent.start(run)
    finally:
        agent.close()
    return store.load(run.run_id)


def parse_repeats(text: str) -> dict[str, int]:
    """'A=3,B=5,C=5,D=2,hand=3' -> repeats per generated category and for hand-written targets."""
    out = {}
    for part in text.split(","):
        key, _, n = part.partition("=")
        key = key.strip()
        if key not in ("A", "B", "C", "D", "hand") or not n.strip().isdigit():
            raise SystemExit(f"--repeats: bad entry {part!r} (use e.g. A=3,B=5,C=5,D=2,hand=3)")
        out[key] = int(n)
    return out


def seeds_per_target(targets: list[dict], first_seed: int, n_seeds: int, repeats: dict | None) -> dict[str, list[int]]:
    """Seeds for each target: n_seeds for all, or by category / hand with --repeats (missing key = 0)."""
    def n(t):
        return n_seeds if repeats is None else repeats.get("hand" if t["source"] == "hand" else t["category"], 0)
    return {t["id"]: list(range(first_seed, first_seed + n(t))) for t in targets}


def plan_runs(version: str, method: str, targets: list[dict], seeds: list[int] | dict[str, list[int]],
              done: set) -> list[tuple]:
    """(target, seed, oracle chain) still to run; seeds is one list for all targets or a list per target id."""
    oracle = {}
    if method == "random_fixed_topology_oracle":
        sol = read_solutions(version)
        oracle = {t["id"]: [b["block_id"] for b in sol[t["id"]]["chain"]] for t in targets
                  if t["source"] == "generated" and "chain" in sol.get(t["id"], {})}
        targets = [t for t in targets if t["id"] in oracle]
    by_t = seeds if isinstance(seeds, dict) else {t["id"]: seeds for t in targets}
    return [(t, s, oracle.get(t["id"])) for t in targets for s in by_t.get(t["id"], []) if (t["id"], s) not in done]


def main(argv=None, input_fn=input) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", dest="version", default="v1")
    ap.add_argument("--method", required=True, choices=RANDOM_METHODS + AGENT_METHODS)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--first-seed", type=int, default=1)
    ap.add_argument("--targets", default="all")
    ap.add_argument("--repeats", help="repeats per category instead of --seeds, e.g. A=3,B=5,C=5,D=2,hand=3")
    ap.add_argument("--llm", choices=["fake", "real"], default="fake")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    cfg = load_config()
    out_dir = Path(args.out) if args.out else REPO_ROOT / "runs" / "bench" / args.version / args.method
    out_dir.mkdir(parents=True, exist_ok=True)
    targets = select_targets(load_set(args.version), args.targets, args.version)
    repeats = parse_repeats(args.repeats) if args.repeats else None
    seeds = seeds_per_target(targets, args.first_seed, args.seeds, repeats)
    todo = plan_runs(args.version, args.method, targets, seeds, finished(out_dir))
    code = code_version()
    print(f"{args.method}: {len(todo)} runs to do (targets {len(targets)}, "
          f"{'repeats ' + args.repeats if repeats else f'seeds {args.first_seed}-{args.first_seed + args.seeds - 1}'}), "
          f"at most {len(todo) * cfg['run']['sim_budget']} sims; code {code[0][:10]}{' (modified)' if code[1] else ''}; "
          f"out: {out_dir}")
    if args.method in AGENT_METHODS and args.llm == "real" and code[1]:
        print("Refusing a real-LLM batch: tracked files differ from the commit (the evaluated code must be committed).")
        return 1

    llm = None
    if args.method in AGENT_METHODS:
        if args.llm == "real":
            if not todo or not confirm_real(len(todo), cfg, input_fn):
                print("Not confirmed: no API call made.")
                return 1
            from pedal_agent.llm import make_real_llm       # client chosen in config.yaml llm.client
            llm = make_real_llm(cfg)
        else:
            llm = None                                   # a fresh fake script per run (below)

    from pedal_agent.llm import LLMInfraError, UsageLimitError
    store = RunStore(out_dir)
    t0 = time.time()
    for i, (t, seed, oracle_chain) in enumerate(todo, 1):
        run_llm = fake_llm() if args.method in AGENT_METHODS and args.llm == "fake" else llm
        try:
            rec = run_one(args.version, t, args.method, seed, store, run_llm, oracle_chain, code)
        except LLMInfraError as e:                       # the run itself is saved as infra_error (re-run on resume)
            why = ("Usage limit reached" if isinstance(e, UsageLimitError) else "LLM infrastructure error")
            print(f"\n{why} after {i - 1} of {len(todo)} runs: {e}")
            if isinstance(e, UsageLimitError):
                print("The allowance refills within about 6 hours.")
            print("Finished runs are kept. Resume later with the same command:\n  python -m scripts.run_benchmark "
                  + " ".join(argv if argv is not None else sys.argv[1:]))
            return 3
        print(f"[{time.time() - t0:6.0f}s] {i}/{len(todo)} {t['id']} seed {seed}: {rec.stop_reason} "
              f"after {rec.sims_used} sims", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
