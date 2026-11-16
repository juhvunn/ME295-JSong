"""Stratified target subset for the expensive (agent) benchmark runs (docs/phase3_plan.md, P3).

Chosen with a fixed seed from the category LABELS only (never from any run result), weighted toward
the categories that answer the research question: generated A 2, B 4, C 4, D 1, plus 1 hand target.
Written to benchmarks/<version>_subset.yaml and committed before any agent run.

Usage: python -m scripts.make_subset --version v1 --seed 2611
"""
import argparse
import random
import sys

import yaml

from pedal_agent.config import REPO_ROOT

B = REPO_ROOT / "benchmarks"
QUOTA = {("generated", "A"): 2, ("generated", "B"): 4, ("generated", "C"): 4, ("generated", "D"): 1, ("hand", None): 1}


def choose(targets: list[dict], seed: int) -> list[str]:
    rng = random.Random(seed)
    ids = []
    for (source, cat), n in QUOTA.items():
        pool = sorted(t["id"] for t in targets if t["source"] == source and (cat is None or t["category"] == cat))
        ids += sorted(rng.sample(pool, n))
    return ids


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v1")
    ap.add_argument("--seed", type=int, default=2611)
    args = ap.parse_args(argv)
    targets = yaml.safe_load((B / f"{args.version}.yaml").read_text(encoding="utf-8"))["targets"]
    ids = choose(targets, args.seed)
    out = {"version": args.version, "seed": args.seed,
           "rule": "random.Random(seed).sample per stratum over sorted ids, from category labels only: "
                   "generated A 2, B 4, C 4, D 1; hand 1",
           "targets": ids}
    path = B / f"{args.version}_subset.yaml"
    path.write_text("# Stratified subset for agent runs. Fixed before any agent run; never edit after results.\n" +
                    yaml.safe_dump(out, sort_keys=False), encoding="utf-8", newline="\n")
    print(path, ids)
    return 0


if __name__ == "__main__":
    sys.exit(main())
