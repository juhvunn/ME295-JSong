"""Summarize benchmark RunRecords (docs/phase3_plan.md, step 4). Reads RunRecords only.

Outputs in --out (default results/bench_<set>/):
  summary.md            success per method x group (A, B, C, D generated; Hand; All) with run counts, for the
                        full set and the SUBSET view (all methods on exactly the subset targets), plus details
                        (median sims to success, median best score, topology changes, wall time, flagged runs,
                        tokens, cost) and a per-target table
  per_target.csv        successes / runs and median sims to success per target x method
  success_vs_sims.csv   cumulative fraction of runs solved by simulation k = 1..budget, per view x group x method
  success_vs_sims.png / success_vs_sims_subset.png

Usage: python -m scripts.summarize_benchmark runs/bench/v1 [--set v1] [--out results/bench_v1]
"""
import argparse
import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import yaml

from pedal_agent.config import REPO_ROOT
from pedal_agent.schemas import RunRecord

B = REPO_ROOT / "benchmarks"
METHODS = ("agent", "baseline_fixed_topology", "random_catalog", "random_fixed_topology", "random_fixed_topology_oracle")
SHORT = {"agent": "agent", "baseline_fixed_topology": "agent fixed-topo", "random_catalog": "random catalog",
         "random_fixed_topology": "random fixed-topo", "random_fixed_topology_oracle": "oracle"}
# fixed method -> colour (dataviz reference categorical slots 1-5, light mode) and marker: colour follows the method
COLOR = dict(zip(METHODS, ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4")))
MARKER = dict(zip(METHODS, ("o", "s", "^", "D", "v")))
GROUPS = ("A", "B", "C", "D", "Hand", "All")


def load_runs(root: Path) -> list[RunRecord]:
    runs = []
    for p in sorted(root.rglob("*.json")):
        r = RunRecord.model_validate_json(p.read_text(encoding="utf-8"))
        if r.benchmark is not None and r.stop_reason is not None:
            runs.append(r)
    return runs


def group_of(run: RunRecord, source: dict) -> str:
    return "Hand" if source.get(run.benchmark.target_id) == "hand" else run.benchmark.category


def success(r: RunRecord) -> bool:
    return r.stop_reason == "all_pass"


def wall_s(r: RunRecord) -> float:
    return (r.steps[-1].at - r.created_at).total_seconds() if r.steps else 0.0


def median(xs):
    return statistics.median(xs) if xs else None


def fmt(x, spec=".3g"):
    return "–" if x is None else format(x, spec)


def cumulative(runs: list[RunRecord], budget: int) -> list[float]:
    n = len(runs)
    return [sum(success(r) and r.sims_used <= k for r in runs) / n if n else 0.0 for k in range(1, budget + 1)]


def by_group(runs, source):
    g = defaultdict(lambda: defaultdict(list))         # group -> method -> runs
    for r in runs:
        g[group_of(r, source)][r.mode].append(r)
        g["All"][r.mode].append(r)
    return g


def success_table(title, groups, methods):
    L = [f"## {title}", "", "Success rate (successful runs / runs).", "",
         "| Group | " + " | ".join(SHORT[m] for m in methods) + " |", "|---|" + "---|" * len(methods)]
    for grp in GROUPS:
        if grp not in groups:
            continue
        cells = []
        for m in methods:
            rs = groups[grp].get(m, [])
            k = sum(map(success, rs))
            cells.append(f"{100 * k / len(rs):.0f} % ({k}/{len(rs)})" if rs else "–")
        L.append(f"| {grp} | " + " | ".join(cells) + " |")
    return L + [""]


def details_table(title, groups, methods):
    L = [f"## {title}", "",
         "| Method | Group | Runs | Success | Median sims to success | Median best score | Mean topology changes | "
         "Median wall s | Flagged runs | Tokens in/out | Cost USD |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for m in methods:
        for grp in GROUPS:
            rs = groups.get(grp, {}).get(m, [])
            if not rs:
                continue
            ok = [r for r in rs if success(r)]
            best = [r.best.report.score for r in rs if r.best and r.best.report]
            L.append(f"| {SHORT[m]} | {grp} | {len(rs)} | {100 * len(ok) / len(rs):.0f} % | "
                     f"{fmt(median([r.sims_used for r in ok]))} | {fmt(median(best))} | "
                     f"{statistics.mean(r.topology_changes for r in rs):.2f} | {fmt(median([wall_s(r) for r in rs]), '.1f')} | "
                     f"{sum(bool(r.placeholder_or_unvalidated) for r in rs)} | "
                     f"{sum(r.input_tokens for r in rs)}/{sum(r.output_tokens for r in rs)} | "
                     f"{sum(r.cost_usd for r in rs):.2f} |")
    return L + [""]


def plot(path, groups, methods, budget, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    shown = [g for g in GROUPS if g in groups]
    shown = ["All"] + [g for g in shown if g != "All"]
    fig, axes = plt.subplots(2, 3, figsize=(12, 7), sharex=True, sharey=True)
    ks = list(range(1, budget + 1))
    for ax, grp in zip(axes.flat, shown):
        for m in methods:
            rs = groups[grp].get(m, [])
            if rs:
                ax.plot(ks, cumulative(rs, budget), color=COLOR[m], marker=MARKER[m], markersize=5,
                        linewidth=2, label=f"{SHORT[m]} (n={len(rs)})")
        n_t = len({r.benchmark.target_id for m in methods for r in groups[grp].get(m, [])})
        ax.set_title(f"{grp} ({n_t} targets)", fontsize=11, loc="left")
        ax.set_ylim(0, 1)
        ax.set_xticks([1, 3, 6, 9, 12] if budget == 12 else ks)
        ax.grid(color="#e5e5e2", linewidth=0.8)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        if ax.get_legend_handles_labels()[0]:
            ax.legend(fontsize=7, frameon=False, loc="upper left")
    for ax in axes.flat[len(shown):]:
        ax.set_visible(False)
    for ax in axes[-1]:
        ax.set_xlabel("simulations used")
    for ax in axes[:, 0]:
        ax.set_ylabel("fraction of runs solved")
    fig.suptitle(title, x=0.01, ha="left", fontsize=12)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("--set", dest="version", default="v1")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    out = args.out or REPO_ROOT / "results" / f"bench_{args.version}"
    out.mkdir(parents=True, exist_ok=True)
    targets = yaml.safe_load((B / f"{args.version}.yaml").read_text(encoding="utf-8"))["targets"]
    source = {t["id"]: t["source"] for t in targets}
    subset_file = B / f"{args.version}_subset.yaml"
    subset = set(yaml.safe_load(subset_file.read_text(encoding="utf-8"))["targets"]) if subset_file.exists() else set()
    runs = [r for r in load_runs(args.root) if r.benchmark.set == args.version]
    methods = [m for m in METHODS if any(r.mode == m for r in runs)]
    budget = max((r.sim_budget for r in runs), default=12)
    full = by_group(runs, source)
    sub = by_group([r for r in runs if r.benchmark.target_id in subset], source)

    L = [f"# Benchmark {args.version}: summary", "",
         f"{len(runs)} finished runs from `{args.root}`; methods: {', '.join(methods)}; budget {budget} sims. "
         "Success = all metrics in range (stop_reason all_pass). The oracle is not run on D or hand targets.", ""]
    L += success_table("Full set", full, methods)
    if subset:
        L += success_table(f"Subset view ({len(subset)} targets: {', '.join(sorted(subset))}); random methods "
                           "filtered from their full-set runs", sub, methods)
    L += details_table("Details (full set)", full, methods)

    per = defaultdict(dict)
    for r in runs:
        per[r.benchmark.target_id].setdefault(r.mode, []).append(r)
    L += ["## Per target (successes / runs; median sims to success)", "",
          "| Target | Cat. | Subset | " + " | ".join(SHORT[m] for m in methods) + " |", "|---|---|---|" + "---|" * len(methods)]
    rows = []
    for t in targets:
        if t["id"] not in per:
            continue
        cells = []
        for m in methods:
            rs = per[t["id"]].get(m, [])
            ok = [r.sims_used for r in rs if success(r)]
            cells.append(f"{len(ok)}/{len(rs)} ({fmt(median(ok))})" if rs else "–")
            rows.append({"target": t["id"], "category": t["category"], "source": t["source"], "subset": t["id"] in subset,
                         "method": m, "runs": len(rs), "successes": len(ok), "median_sims_to_success": median(ok)})
        L.append(f"| {t['id']} | {t['category']} | {'✓' if t['id'] in subset else ''} | " + " | ".join(cells) + " |")
    (out / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")

    with (out / "per_target.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["target"])
        w.writeheader()
        w.writerows(rows)
    with (out / "success_vs_sims.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["view", "group", "method", "runs", *[f"k{k}" for k in range(1, budget + 1)]])
        for view, groups in (("full", full), ("subset", sub)):
            for grp in GROUPS:
                for m in methods:
                    rs = groups.get(grp, {}).get(m, [])
                    if rs:
                        w.writerow([view, grp, m, len(rs), *[f"{x:.4f}" for x in cumulative(rs, budget)]])
    plot(out / "success_vs_sims.png", full, methods, budget, f"Benchmark {args.version}: cumulative success vs simulations (full set)")
    if subset:
        plot(out / "success_vs_sims_subset.png", sub, methods, budget,
             f"Benchmark {args.version}: cumulative success vs simulations (subset, {len(subset)} targets)")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
