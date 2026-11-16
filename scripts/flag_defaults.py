"""Analysis flag per generated target: does the hidden solution's CHAIN at its default settings already
pass the target? (docs/phase3_plan.md, limitations.) Separates "picked the right chain" from "picked
the chain and tuned it" in the summary.

Derived from the hidden solutions file: ANALYSIS ONLY. No planner, baseline or runner may read the output.
Writes benchmarks/<version>_solutions_analysis.yaml.

Usage: python -m scripts.flag_defaults --version v1
"""
import argparse
import sys

import yaml

from pedal_agent.checker import check
from pedal_agent.config import REPO_ROOT
from pedal_agent.schemas import BlockInstance, Candidate, MetricTarget, TargetSpec

B = REPO_ROOT / "benchmarks"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v1")
    args = ap.parse_args(argv)
    targets = yaml.safe_load((B / f"{args.version}.yaml").read_text(encoding="utf-8"))["targets"]
    sol = yaml.safe_load((B / f"{args.version}_solutions.yaml").read_text(encoding="utf-8"))
    flags = {}
    for t in targets:
        if t["source"] != "generated" or "chain" not in sol.get(t["id"], {}):
            continue
        chain = [b["block_id"] for b in sol[t["id"]]["chain"]]
        spec = TargetSpec(goal_text=t["label"], targets=[MetricTarget(**x) for x in t["targets"]])
        rep = check(Candidate(chain=[BlockInstance(block_id=b) for b in chain], rationale=""), spec)
        flags[t["id"]] = {"chain": " -> ".join(chain), "category": t["category"],
                          "passes_at_defaults": bool(rep.dc_ok and not rep.errors and rep.results and
                                                     all(r.status == "pass" for r in rep.results))}
        print(t["id"], flags[t["id"]])
    path = B / f"{args.version}_solutions_analysis.yaml"
    path.write_text("# ANALYSIS ONLY (derived from the hidden solutions): no planner, baseline or runner may read this.\n"
                    "# passes_at_defaults: the solution's chain at default settings already passes the target.\n" +
                    yaml.safe_dump({"version": args.version, "targets": flags}, sort_keys=False),
                    encoding="utf-8", newline="\n")
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
