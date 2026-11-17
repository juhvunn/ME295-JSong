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


def load_runs(root: Path, infra: list | None = None) -> list[RunRecord]:
    """Finished benchmark runs. infra_error runs (exceptions outside the method; they are re-run) are left
    out and, if a list is given, collected in it for reporting."""
    runs = []
    for p in sorted(root.rglob("*.json")):
        r = RunRecord.model_validate_json(p.read_text(encoding="utf-8"))
        if r.benchmark is None or r.stop_reason is None:
            continue
        if r.stop_reason == "infra_error":
            if infra is not None:
                infra.append(r)
            continue
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


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95 % Wilson score interval for k successes in n runs (fractions)."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / (1 + z * z / n)
    return max(0.0, c - h), min(1.0, c + h)


def success_table(title, groups, methods, ci=False):
    note = "Success rate (successful runs / runs" + (", 95 % Wilson interval)." if ci else ").")
    L = [f"## {title}", "", note, "",
         "| Group | " + " | ".join(SHORT[m] for m in methods) + " |", "|---|" + "---|" * len(methods)]
    for grp in GROUPS:
        if grp not in groups:
            continue
        cells = []
        for m in methods:
            rs = groups[grp].get(m, [])
            k = sum(map(success, rs))
            if not rs:
                cells.append("–")
                continue
            cell = f"{100 * k / len(rs):.0f} % ({k}/{len(rs)})"
            if ci:
                lo, hi = wilson(k, len(rs))
                cell += f" [{100 * lo:.0f}–{100 * hi:.0f}]"
            cells.append(cell)
        L.append(f"| {grp} | " + " | ".join(cells) + " |")
    return L + [""]


def two_block_chains(r: RunRecord) -> list[tuple[str, ...]]:
    """Ordered 2-block chains this run simulated (start step included)."""
    return [tuple(b.block_id for b in s.candidate.chain) for s in r.steps
            if s.report is not None and s.candidate is not None and len(s.candidate.chain) == 2]


def order_table(runs: list[RunRecord], methods, solution_chain: dict[str, str], title: str) -> list[str]:
    """How often the same two blocks were tried in both orders; for C targets, whether the solution's order
    (from the analysis file) or only the reversed order was tried."""
    L = [f"## {title}", "",
         "Runs that simulated at least one 2-block chain; of those, runs that tried the same two blocks in both "
         "orders. C targets: runs that tried the solution's order vs only the reversed order (solution chain from "
         "the analysis file).", "",
         "| Method | Runs | With a 2-block chain | Both orders of a pair | C runs | C: solution order tried | "
         "C: only reversed order tried |", "|---|---|---|---|---|---|---|"]
    for m in methods:
        rs = [r for r in runs if r.mode == m]
        if not rs:
            continue
        with2 = [r for r in rs if two_block_chains(r)]
        both = [r for r in with2 if any((b, a) in set(two_block_chains(r)) for a, b in two_block_chains(r))]
        c_runs = [r for r in rs if r.benchmark.category == "C" and r.benchmark.target_id in solution_chain]
        sol_tried = rev_only = 0
        for r in c_runs:
            sol = tuple(solution_chain[r.benchmark.target_id].split(" -> "))
            tried = set(two_block_chains(r))
            sol_tried += sol in tried
            rev_only += sol not in tried and tuple(reversed(sol)) in tried
        L.append(f"| {SHORT[m]} | {len(rs)} | {len(with2)} | {len(both)} | {len(c_runs)} | {sol_tried} | {rev_only} |")
    return L + [""]


def c_split_table(title, runs, methods, defaults_pass):
    """C targets split by the analysis flag: the solution's chain at defaults already passes or not."""
    L = [f"## {title}", "", "C targets split by whether the solution's chain at its default settings already "
         "passes (analysis flag from `scripts/flag_defaults.py`).", "",
         "| C targets | " + " | ".join(SHORT[m] for m in methods) + " |", "|---|" + "---|" * len(methods)]
    c_runs = [r for r in runs if r.benchmark.category == "C" and r.benchmark.target_id in defaults_pass]
    for flag, label in ((True, "chain at defaults passes"), (False, "needs tuning")):
        ids = sorted({t for t, v in defaults_pass.items() if v is flag} & {r.benchmark.target_id for r in c_runs})
        cells = []
        for m in methods:
            rs = [r for r in c_runs if r.mode == m and defaults_pass[r.benchmark.target_id] is flag]
            k = sum(map(success, rs))
            cells.append(f"{100 * k / len(rs):.0f} % ({k}/{len(rs)})" if rs else "–")
        L.append(f"| {label} ({', '.join(ids) or 'none'}) | " + " | ".join(cells) + " |")
    return L + [""]


def details_table(title, groups, methods):
    L = [f"## {title}", "",
         "| Method | Group | Runs | Success | Median sims to success | Median best score | Mean topology changes | "
         "Median wall s | Flagged runs | Tokens in/out | API-equivalent cost USD (no per-token billing) |", "|---|---|---|---|---|---|---|---|---|---|---|"]
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
                     f"{sum(r.api_equivalent_cost_usd for r in rs):.2f} |")
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
    flag_file = B / f"{args.version}_solutions_analysis.yaml"       # analysis only (scripts/flag_defaults.py)
    defaults_pass = ({tid: v["passes_at_defaults"] for tid, v in
                      yaml.safe_load(flag_file.read_text(encoding="utf-8"))["targets"].items()}
                     if flag_file.exists() else {})
    infra = []
    runs = [r for r in load_runs(args.root, infra) if r.benchmark.set == args.version]
    methods = [m for m in METHODS if any(r.mode == m for r in runs)]
    budget = max((r.sim_budget for r in runs), default=12)
    full = by_group(runs, source)
    sub = by_group([r for r in runs if r.benchmark.target_id in subset], source)

    L = [f"# Benchmark {args.version}: summary", "",
         f"{len(runs)} finished runs from `{args.root}`; methods: {', '.join(methods)}; budget {budget} sims. "
         "Success = all metrics in range (stop_reason all_pass). The oracle is not run on D or hand targets. "
         f"Infrastructure errors left out (re-run): {len(infra)}"
         + (" (" + ", ".join(f"{r.benchmark.target_id}/{r.mode}/seed {r.seed}" for r in infra) + ")" if infra else "")
         + ".", ""]
    commits = defaultdict(lambda: defaultdict(int))     # method -> commit (+ modified) -> runs
    for r in runs:
        key = "not recorded" if r.code_commit is None else r.code_commit[:10] + (" (modified)" if r.code_dirty else "")
        commits[r.mode][key] += 1
    L += ["Code commits per method (runs): " + "; ".join(
        f"{SHORT[m]}: " + ", ".join(f"{c} ×{n}" for c, n in commits[m].items()) for m in methods if m in commits), ""]
    L += success_table("Full set", full, methods, ci=True)
    if subset:
        L += success_table(f"Subset view ({len(subset)} targets: {', '.join(sorted(subset))}); all methods on exactly "
                           "these targets (random methods filtered from their full-set runs)", sub, methods, ci=True)
    if defaults_pass:
        L += c_split_table("C split (full set)", runs, methods, defaults_pass)
        if subset:
            L += c_split_table("C split (subset)", [r for r in runs if r.benchmark.target_id in subset], methods,
                               defaults_pass)
    solution_chain = ({tid: v["chain"] for tid, v in yaml.safe_load(flag_file.read_text(encoding="utf-8"))["targets"].items()}
                      if flag_file.exists() else {})
    L += order_table(runs, methods, solution_chain, "Block order, full set (2-block chains)")
    if subset:
        L += order_table([r for r in runs if r.benchmark.target_id in subset], methods, solution_chain,
                         "Block order, subset (2-block chains)")
    L += details_table("Details (full set)", full, methods)

    per = defaultdict(dict)
    for r in runs:
        per[r.benchmark.target_id].setdefault(r.mode, []).append(r)
    L += ["## Per target (successes / runs; median sims to success)", "",
          "Defaults pass = the solution's chain at default settings already passes (analysis flag).", "",
          "| Target | Cat. | Subset | Defaults pass | " + " | ".join(SHORT[m] for m in methods) + " |",
          "|---|---|---|---|" + "---|" * len(methods)]
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
                         "defaults_pass": defaults_pass.get(t["id"]), "method": m, "runs": len(rs), "successes": len(ok), "median_sims_to_success": median(ok)})
        dp = {True: "yes", False: "no"}.get(defaults_pass.get(t["id"]), "–")
        L.append(f"| {t['id']} | {t['category']} | {'✓' if t['id'] in subset else ''} | {dp} | " + " | ".join(cells) + " |")
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
