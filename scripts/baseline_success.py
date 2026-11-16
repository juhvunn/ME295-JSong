"""Quick difficulty check of a benchmark set with the three AI-free baselines (no API cost).

The random planners never read Checker feedback, so the designs a run proposes depend only on the
planner seed (and, for the oracle, the solution's chain). Each design sequence is therefore simulated
ONCE and every target is scored against it: success = any of the sim_budget simulated steps passes
all windows (step 1 = the start chain at its defaults, then sim_budget - 1 planner proposals), which
is what a full benchmark run records (pass at sim k stops the run, it does not change success).
--crosscheck N also runs N targets x 1 seed through the real graph (Agent) and compares.

Usage: python -m scripts.baseline_success --version v1 --seeds 20
"""
import argparse
import sys
from collections import defaultdict

import yaml

from pedal_agent.baselines.planners import RandomCatalogPlanner, RandomFixedTopologyPlanner
from pedal_agent.checker import check
from pedal_agent.config import REPO_ROOT, load_config
from pedal_agent.schemas import BlockInstance, Candidate, MetricTarget, TargetSpec

B = REPO_ROOT / "benchmarks"
EMPTY = TargetSpec(goal_text="baseline check", targets=[])
START = ["od_ts808"]
METHODS = ("random_catalog", "random_fixed_topology", "random_fixed_topology_oracle")


def passes(metrics, targets):
    return bool(metrics) and all((t["lo"] is None or metrics[t["name"]] >= t["lo"]) and
                                 (t["hi"] is None or metrics[t["name"]] <= t["hi"]) for t in targets)


def metrics_of(design):
    rep = check(Candidate(chain=[BlockInstance(block_id=b, params=p) for b, p in design], rationale=""), EMPTY)
    return rep.metrics if rep.dc_ok and not rep.errors else {}


def sequence(planner, start_chain, n):
    """Metrics of the start step and n planner proposals."""
    return [metrics_of([(b, {}) for b in start_chain])] + [metrics_of(planner.design()) for _ in range(n)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v1")
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--crosscheck", type=int, default=0)
    args = ap.parse_args(argv)
    budget = load_config()["run"]["sim_budget"]
    targets = yaml.safe_load((B / f"{args.version}.yaml").read_text(encoding="utf-8"))["targets"]
    sol = yaml.safe_load((B / f"{args.version}_solutions.yaml").read_text(encoding="utf-8"))
    # oracle only for generated targets: a hand target's stored "solution" is just the first passing pool
    # design found during classification, so its chain is arbitrary (docs/phase3_plan.md)
    oracle_chain = {t["id"]: tuple(b["block_id"] for b in sol[t["id"]]["chain"])
                    for t in targets if t["source"] == "generated" and "chain" in sol.get(t["id"], {})}
    seeds = range(1, args.seeds + 1)

    seqs = {}
    for s in seeds:
        seqs[("random_catalog", s)] = sequence(RandomCatalogPlanner(s, START), START, budget - 1)
        seqs[("random_fixed_topology", s)] = sequence(RandomFixedTopologyPlanner(s, START), START, budget - 1)
        for c in sorted(set(oracle_chain.values())):
            seqs[(c, s)] = sequence(RandomFixedTopologyPlanner(s, list(c)), list(c), budget - 1)
        print(f"seed {s} done", flush=True)

    rows = {}
    for t in targets:
        r = {}
        for m in METHODS:
            key = oracle_chain.get(t["id"]) if m == "random_fixed_topology_oracle" else m
            r[m] = None if key is None else sum(any(passes(x, t["targets"]) for x in seqs[(key, s)]) for s in seeds)
        rows[t["id"]] = r

    n = args.seeds
    print(f"\nPer target: successes of {n} seeds (budget {budget} sims; oracle n/a for D and hand targets)")
    print(f"{'id':5} {'cat':3} " + " ".join(f"{m:>28}" for m in METHODS))
    for t in targets:
        print(f"{t['id']:5} {t['category']:3} " + " ".join(f"{'n/a' if v is None else v:>28}" for v in rows[t['id']].values()))
    for src in ("generated", "hand"):
        print(f"\nSuccess rate by category ({src} targets; mean over targets and seeds)")
        print(f"{'cat':4} {'n':>3} " + " ".join(f"{m:>28}" for m in METHODS))
        agg = defaultdict(list)
        for t in targets:
            if t["source"] == src:
                agg[t["category"]].append(rows[t["id"]])
        for cat in "ABCD":
            if cat in agg:
                cells = []
                for m in METHODS:
                    v = [r[m] for r in agg[cat] if r[m] is not None]
                    cells.append(f"{100 * sum(v) / (n * len(v)):.0f} % ({len(v)} tg)" if v else "n/a")
                print(f"{cat:4} {len(agg[cat]):>3} " + " ".join(f"{c:>28}" for c in cells))

    if args.crosscheck:
        from pedal_agent.graph import Agent, RunStore, new_benchmark_run
        from pedal_agent.schemas import BenchmarkRef
        import tempfile
        print("\nCross-check against the real graph (seed 1):")
        for t in [t for t in targets if t["id"] in oracle_chain][:args.crosscheck]:
            for m in METHODS:
                start = list(oracle_chain[t["id"]]) if m == "random_fixed_topology_oracle" else START
                planner = RandomCatalogPlanner(1, START) if m == "random_catalog" else RandomFixedTopologyPlanner(1, start)
                with tempfile.TemporaryDirectory() as d:
                    agent = Agent(planner, RunStore(d))
                    ref = BenchmarkRef(set=args.version, target_id=t["id"], category=t["category"],
                                       start_chain=[BlockInstance(block_id=b) for b in start])
                    spec = TargetSpec(goal_text=t["label"], targets=[MetricTarget(**x) for x in t["targets"]])
                    run = new_benchmark_run(spec, ref, planner, mode=m, seed=1)
                    agent.start(run)
                    agent.close()
                    rec = agent.store.load(run.run_id)
                key = oracle_chain[t["id"]] if m == "random_fixed_topology_oracle" else m
                quick = any(passes(x, t["targets"]) for x in seqs[(key, 1)])
                print(f"  {t['id']} {m}: graph stop_reason={rec.stop_reason} sims={rec.sims_used} "
                      f"success={rec.stop_reason == 'all_pass'}  quick={quick}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
