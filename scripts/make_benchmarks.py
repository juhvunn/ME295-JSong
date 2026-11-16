"""Generate a benchmark target set (docs/phase3_plan.md, sections 1 and 4b).

1. Sample pool: a fixed number of draws per chain (3 single blocks + 4 two-block chains) from the
   GENERATOR distribution (pedal_agent.baselines.sampling.generator_params: different from the random
   baselines). Draws that pass the DC checks are the pool; it gives the metric spreads, the
   classification evidence and the hit rates (passes / draws, so DC failures count as misses).
2. Metric eligibility per chain: 10-90 % spread over the playable pool (out_pk_v >= 0.05 V) >= 2 x the
   base window width. thd_pct counts only where THD >= 10 x the Checker's measured floor, even_odd only
   where THD >= 1 % (below that the harmonic ratio is measurement noise).
3. Generated targets: draw a solution on a chain chosen for the category still to fill; keep it only if
   the DC checks pass and out_pk_v >= 0.05 V; pick 3-4 eligible metrics that are meaningful for the
   solution; set windows around the measured values; CALIBRATE: widen all windows by a common factor
   (1 ... 4) until the hit rate on the solution's chain reaches 5 % (redraw if it never does); exclude it if od_ts808 at its
   defaults passes; re-check that the solution passes; classify:
     A  the solution is the start chain, or >= 1 start-chain pool sample passes
     B  0 start-chain samples pass, solution is another single block
        (or a 2-block solution where some other single block's samples pass)
     C  0 samples pass for every single block, solution is a 2-block chain
4. Likely-unreachable targets (D): pairs of metric bounds at quantiles of the playable pool that no
   pool sample meets jointly.
5. Hand-written targets (benchmarks/<version>_hand_targets.yaml): never changed; classified with the
   pool evidence and their hit rates reported; the first passing pool design is stored as their solution.
Outputs: benchmarks/<v>.yaml (targets + evidence), benchmarks/<v>_solutions.yaml (hidden),
benchmarks/<v>_report.md (spreads, counts, target table).

Usage: python -m scripts.make_benchmarks --version v1 --seed 1116
"""
import argparse
import itertools
import math
import random
import subprocess
import sys
import time
from datetime import datetime, timezone

import numpy as np
import yaml

from pedal_agent.baselines.sampling import generator_design, order_chain
from pedal_agent.checker import THD_FLOOR_PCT, check, model_paths
from pedal_agent.config import REPO_ROOT
from pedal_agent.provenance import describe
from pedal_agent.schemas import BlockInstance, Candidate, MetricTarget, TargetSpec
from pedal_agent.validate import block_ids

OUT = REPO_ROOT / "benchmarks"
START = ("od_ts808",)
METRICS = ("gain_1k_db", "thd_pct", "ac_peak_hz", "ac_peak_db", "even_odd", "out_pk_v")
UNIT = {"gain_1k_db": "dB", "ac_peak_db": "dB", "thd_pct": "%", "ac_peak_hz": "Hz", "even_odd": "", "out_pk_v": "V"}
LABEL = {"gain_1k_db": "Gain at 1 kHz", "ac_peak_db": "Response peak level", "thd_pct": "THD (300 mV)",
         "ac_peak_hz": "Response peak", "even_odd": "Even/odd harmonics", "out_pk_v": "Output peak"}
QUOTAS = {"A": 7, "B": 9, "C": 10}
N_UNREACHABLE = 4
DRAWS_PER_CHAIN = 250
EMPTY = TargetSpec(goal_text="benchmark generation", targets=[])
# base windows (factor 1); calibration multiplies the half-width (dB, even_odd +-0.02) or the exponent (ratios)
LOG_RATIO = {"thd_pct": 1.25, "ac_peak_hz": 1.25, "out_pk_v": 1.2}
DB_HALF = 1.5
EO_RATIO, EO_ABS = 1.5, 0.02
# floors
OUT_PK_MIN = 0.05                 # V: a solution must be audible into an amp ("playable")
THD_MIN = 10 * THD_FLOOR_PCT      # %: 10 x the Checker's measured THD floor (tests/test_checker_floor.py)
EO_THD_MIN = 1.0                  # %: even_odd only meaningful above this THD
# difficulty calibration
TARGET_HIT = 0.05                 # hit rate on the solution's chain (12-sim oracle: 1 - 0.95**12 = 46 %)
FACTORS = (1.0, 1.15, 1.3, 1.5, 1.75, 2.0, 2.3, 2.6, 3.0, 3.5, 4.0)


def window(name, m, f=1.0):
    if name in ("gain_1k_db", "ac_peak_db"):
        return m - DB_HALF * f, m + DB_HALF * f
    if name in LOG_RATIO:
        return m / LOG_RATIO[name] ** f, m * LOG_RATIO[name] ** f
    lo, hi = min(m / EO_RATIO ** f, m - EO_ABS * f), max(m * EO_RATIO ** f, m + EO_ABS * f)   # even_odd
    return max(lo, 0.0), hi


def meaningful(name, metrics):
    """Is this metric's value above the measurement floor for this design?"""
    if name == "thd_pct":
        return metrics["thd_pct"] >= THD_MIN
    if name == "even_odd":
        return metrics["thd_pct"] >= EO_THD_MIN
    return True


def playable(samples):
    return [s for s in samples if s[1]["out_pk_v"] >= OUT_PK_MIN]


def values(samples, name):
    """Metric values over the playable samples where the metric is meaningful."""
    return np.array([m[name] for _, m in playable(samples) if meaningful(name, m)])


def spread_ok(name, vals):
    if len(vals) < 20:
        return False, float("nan")
    p10, p50, p90 = np.percentile(vals, [10, 50, 90])
    if name in ("gain_1k_db", "ac_peak_db"):
        return p90 - p10 >= 2 * 2 * DB_HALF, p90 - p10
    if name in LOG_RATIO:
        s = math.log10(max(p90, 1e-12) / max(p10, 1e-12))
        return s >= 2 * math.log10(LOG_RATIO[name] ** 2), s
    lo, hi = window(name, p50)
    return p90 - p10 >= 2 * (hi - lo), p90 - p10


def all_chains():
    singles = [(b,) for b in block_ids()]
    doubles = sorted({tuple(order_chain(list(p))) for p in itertools.permutations(block_ids(), 2)})
    return singles, doubles


def simulate(design):
    cand = Candidate(chain=[BlockInstance(block_id=b, params=p) for b, p in design], rationale="")
    return check(cand, EMPTY)


def passes(metrics, targets):
    return all((t["lo"] is None or metrics[t["name"]] >= t["lo"]) and (t["hi"] is None or metrics[t["name"]] <= t["hi"])
               for t in targets)


def count(pool_samples, targets):
    return [len(pool_samples), sum(passes(m, targets) for _, m in pool_samples)]


def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()
    except OSError:
        return "unknown"


def mk_targets(names, metrics, f=1.0):
    out = []
    for n in names:
        lo, hi = window(n, metrics[n], f)
        out.append({"name": n, "lo": float(f"{lo:.4g}"), "hi": float(f"{hi:.4g}"), "unit": UNIT[n], "label": LABEL[n]})
    return out


def calibrate(names, metrics, samples, draws):
    """Smallest factor in FACTORS whose hit rate (passes / draws) reaches TARGET_HIT; capped at FACTORS[-1]."""
    hit1 = None
    for f in FACTORS:
        targets = mk_targets(names, metrics, f)
        hits = count(samples, targets)[1]
        hit1 = hits / draws if hit1 is None else hit1
        if hits / draws >= TARGET_HIT:
            break
    return targets, {"factor": f, "hit_rate": round(hits / draws, 4), "hit_rate_factor_1": round(hit1, 4),
                     "hits": hits, "draws": draws, "capped": hits / draws < TARGET_HIT}


def evidence(pool, singles, targets):
    ev = {"start_chain": count(pool[START], targets)}
    ev["single_blocks"] = {c[0]: count(pool[c], targets) for c in singles}
    allp = [s for v in pool.values() for s in v]
    ev["pool_all"] = count(allp, targets)
    return ev


def hit_rates(pool, draws, targets):
    return {" -> ".join(c): round(count(pool[c], targets)[1] / draws[c], 4) for c in pool}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v1")
    ap.add_argument("--seed", type=int, default=1116)
    ap.add_argument("--draws-per-chain", type=int, default=DRAWS_PER_CHAIN)
    ap.add_argument("--max-attempts", type=int, default=3000)
    args = ap.parse_args(argv)
    rng = random.Random(args.seed)
    t0 = time.time()
    singles, doubles = all_chains()
    log = lambda *a: print(f"[{time.time() - t0:6.0f}s]", *a, flush=True)  # noqa: E731

    # 1. pool: fixed number of draws per chain; valid designs kept
    pool, draws = {}, {}
    for chain in singles + doubles:
        pool[chain], draws[chain] = [], args.draws_per_chain
        for _ in range(args.draws_per_chain):
            design = generator_design(rng, list(chain))
            rep = simulate(design)
            if rep.dc_ok and not rep.errors:
                pool[chain].append((design, rep.metrics))
        log(f"pool {' -> '.join(chain)}: {len(pool[chain])} valid of {draws[chain]} draws, "
            f"{len(playable(pool[chain]))} playable")

    # 2. spreads (playable samples, meaningful values only)
    spreads = {}
    for chain, samples in pool.items():
        spreads[chain] = {}
        for n in METRICS:
            vals = values(samples, n)
            ok, s = spread_ok(n, vals)
            p10, p50, p90 = np.percentile(vals, [10, 50, 90]) if len(vals) else (float("nan"),) * 3
            spreads[chain][n] = {"n": int(len(vals)), "p10": float(p10), "p50": float(p50), "p90": float(p90),
                                 "spread": float(s), "eligible": bool(ok)}

    default_metrics = simulate([("od_ts808", {})]).metrics

    # 3. generated targets
    stats = {"attempts": 0, "dc_or_sim_failure": 0, "too_quiet": 0, "too_few_eligible_metrics": 0,
             "calibration_capped": 0, "excluded_default_passes": 0, "self_check_failed": 0, "category_full": 0}
    found = {k: [] for k in QUOTAS}
    while any(len(found[k]) < q for k, q in QUOTAS.items()) and stats["attempts"] < args.max_attempts:
        stats["attempts"] += 1
        want = rng.choice([k for k, q in QUOTAS.items() if len(found[k]) < q])
        chain = START if want == "A" else (rng.choice([c for c in singles if c != START]) if want == "B" else rng.choice(doubles))
        design = generator_design(rng, list(chain))
        rep = simulate(design)
        if not rep.dc_ok or rep.errors:
            stats["dc_or_sim_failure"] += 1
            continue
        if rep.metrics["out_pk_v"] < OUT_PK_MIN:
            stats["too_quiet"] += 1
            continue
        eligible = [n for n in METRICS if spreads[chain][n]["eligible"] and meaningful(n, rep.metrics)]
        if len(eligible) < 3:
            stats["too_few_eligible_metrics"] += 1
            continue
        names = sorted(rng.sample(eligible, min(rng.choice([3, 4]), len(eligible))), key=METRICS.index)
        targets, calib = calibrate(names, rep.metrics, pool[chain], draws[chain])
        if calib["capped"]:                      # still below TARGET_HIT at the cap: redraw
            stats["calibration_capped"] += 1
            continue
        if passes(default_metrics, targets):
            stats["excluded_default_passes"] += 1
            continue
        if not passes(simulate(design).metrics, targets):
            stats["self_check_failed"] += 1
            continue
        ev = evidence(pool, singles, targets)
        if chain == START or ev["start_chain"][1] > 0:
            cat = "A"
        elif len(chain) == 1 or any(v[1] > 0 for v in ev["single_blocks"].values()):
            cat = "B"
        else:
            cat = "C"
        if len(found[cat]) >= QUOTAS[cat]:
            stats["category_full"] += 1
            continue
        found[cat].append({"chain": chain, "design": design, "metrics": rep.metrics, "targets": targets,
                           "evidence": ev, "calibration": calib})
        log(f"target {cat} #{len(found[cat])} on {' -> '.join(chain)}: {names}  factor {calib['factor']} "
            f"hit {calib['hit_rate']:.3f} (at 1: {calib['hit_rate_factor_1']:.3f})  evidence {ev}")

    # 4. likely unreachable (bounds from playable-pool quantiles; THD bounds never below THD_MIN)
    allp = [s for v in pool.values() for s in v]
    q = {n: np.percentile(values(allp, n), [2, 5, 10, 90, 95, 98]) for n in METRICS}
    pairs = [("gain_1k_db", "lo", "thd_pct", "hi"), ("out_pk_v", "lo", "thd_pct", "hi"),
             ("even_odd", "lo", "ac_peak_hz", "lo"), ("thd_pct", "lo", "ac_peak_hz", "lo"),
             ("gain_1k_db", "lo", "even_odd", "lo"), ("ac_peak_hz", "lo", "out_pk_v", "lo"),
             ("ac_peak_db", "lo", "thd_pct", "hi"), ("gain_1k_db", "lo", "ac_peak_hz", "lo"),
             ("even_odd", "lo", "out_pk_v", "lo"), ("ac_peak_hz", "hi", "thd_pct", "hi")]
    unreachable, d_tried = [], 0
    for a, sa, b, sb in pairs:
        if len(unreachable) >= N_UNREACHABLE:
            break
        for tight in (0, 1, 2):          # quantiles p90/p10, p95/p5, p98/p2
            d_tried += 1

            def bound(n, side):
                p2, p5, p10, p90, p95, p98 = q[n]
                x = (p90, p95, p98)[tight] if side == "lo" else (p10, p5, p2)[tight]
                return float(f"{max(x, THD_MIN) if n == 'thd_pct' else x:.4g}")
            targets = [{"name": n, "lo": bound(n, s) if s == "lo" else None, "hi": bound(n, s) if s == "hi" else None,
                        "unit": UNIT[n], "label": LABEL[n]} for n, s in ((a, sa), (b, sb))]
            ev = evidence(pool, singles, targets)
            if ev["pool_all"][1] == 0 and not passes(default_metrics, targets):
                level = ("p90/p10", "p95/p5", "p98/p2")[tight]
                unreachable.append({"targets": targets, "evidence": ev,
                                    "construction": f"{a} {sa}, {b} {sb} at {level} of the playable pool"})
                log(f"unreachable #{len(unreachable)}: {a} {sa} & {b} {sb} ({level})")
                break

    # 5. hand-written targets (unchanged; hit rates reported)
    hand_file = OUT / f"{args.version}_hand_targets.yaml"
    hand = yaml.safe_load(hand_file.read_text(encoding="utf-8"))["targets"]
    hand_out = []
    for h in hand:
        targets = [{"name": t["name"], "lo": t.get("lo"), "hi": t.get("hi"), "unit": t.get("unit", ""), "label": t["label"]}
                   for t in h["targets"]]
        ev = evidence(pool, singles, targets)
        sol, cat = None, "D"
        if ev["start_chain"][1] > 0:
            cat, sol = "A", next(s for s in pool[START] if passes(s[1], targets))
        elif any(v[1] > 0 for v in ev["single_blocks"].values()):
            cat = "B"
            sol = next(s for c in singles for s in pool[c] if passes(s[1], targets))
        elif ev["pool_all"][1] > 0:
            cat = "C"
            sol = next(s for c in doubles for s in pool[c] if passes(s[1], targets))
        hr = hit_rates(pool, draws, targets)
        hand_out.append({"h": h, "targets": targets, "evidence": ev, "category": cat, "solution": sol, "hit_rates": hr})
        log(f"hand {h['id']}: category {cat}, hit rates {hr}")

    # outputs
    rows, solutions = [], {}
    n = 0
    for cat in ("A", "B", "C"):
        for t in found[cat]:
            n += 1
            tid = f"G{n:02d}"
            c = t["calibration"]
            rows.append({"id": tid, "source": "generated", "category": cat, "label": f"generated target {tid}",
                         "targets": t["targets"], "evidence": t["evidence"],
                         "calibration": {"factor": c["factor"], "hit_rate": c["hit_rate"],
                                         "hit_rate_factor_1": c["hit_rate_factor_1"], "capped": c["capped"]}})
            solutions[tid] = {"chain": [{"block_id": b, "params": p} for b, p in t["design"]], "metrics": t["metrics"],
                              "calibration": {**c, "chain": " -> ".join(t["chain"])}}
    for i, u in enumerate(unreachable, 1):
        rows.append({"id": f"U{i}", "source": "generated", "category": "D", "label": f"likely unreachable U{i}",
                     "construction": u["construction"], "targets": u["targets"], "evidence": u["evidence"]})
    for ho in hand_out:
        h = ho["h"]
        rows.append({"id": h["id"], "source": "hand", "category": ho["category"], "label": h["idea"],
                     "targets": ho["targets"], "evidence": ho["evidence"],
                     "hit_rate_best_chain": max(ho["hit_rates"].values())})
        sol = {"hit_rates_by_chain": ho["hit_rates"]}
        if ho["solution"]:
            d, m = ho["solution"]
            sol = {"chain": [{"block_id": b, "params": p} for b, p in d], "metrics": m, **sol}
        solutions[h["id"]] = sol
    for r in rows:                                    # every spec must load as a TargetSpec
        TargetSpec(goal_text=r["label"], targets=[MetricTarget(**t) for t in r["targets"]])

    header = {
        "version": args.version, "seed": args.seed, "git_commit": git_commit(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model_files": [describe(p).model_dump() for p in model_paths()],
        "start_chain": list(START),
        "rules": {"draws_per_chain": args.draws_per_chain, "quotas": {**QUOTAS, "D": N_UNREACHABLE},
                  "base_windows": "gain/ac_peak_db +-1.5 dB; thd/ac_peak_hz x/1.25; out_pk x/1.2; even_odd x/1.5 "
                                  "(>= +-0.02); calibration multiplies the half-width (dB, even_odd) or the exponent",
                  "calibration": f"smallest factor in {list(FACTORS)} with hit rate (passes / draws on the "
                                 f"solution's chain, generator distribution) >= {TARGET_HIT}; capped at {FACTORS[-1]}; "
                                 f"a target still below at the cap is discarded and redrawn",
                  "floors": f"solution out_pk_v >= {OUT_PK_MIN} V; thd_pct used only if THD >= {THD_MIN:.2g} % "
                            f"(10 x measured floor {THD_FLOOR_PCT:.2g} %); even_odd only if THD >= {EO_THD_MIN} %",
                  "eligibility": "10-90 % spread over playable pool (meaningful values) >= 2 x base window width",
                  "sampling": "generator distribution (sampling.generator_params): knobs Beta(0.5,0.5) on [0,1], "
                              "default choice 25 %, parts log-uniform snapped to E-series; validated choices only"},
        "stats": {**stats, "pool_valid": {" -> ".join(c): len(v) for c, v in pool.items()},
                  "unreachable_pairs_tried": d_tried, "seconds": round(time.time() - t0)},
        "categories": {c: sum(r["category"] == c for r in rows) for c in "ABCD"},
    }
    OUT.mkdir(exist_ok=True)
    (OUT / f"{args.version}.yaml").write_text(yaml.safe_dump({"header": header, "targets": rows}, sort_keys=False,
                                                            allow_unicode=True), encoding="utf-8", newline="\n")
    (OUT / f"{args.version}_solutions.yaml").write_text(
        "# HIDDEN SOLUTIONS: for analysis only. No planner, baseline or runner may read this file\n"
        "# (except random_fixed_topology_oracle, which reads only the chain).\n" +
        yaml.safe_dump(solutions, sort_keys=False), encoding="utf-8", newline="\n")
    write_report(args.version, header, rows, spreads, default_metrics, solutions)
    log("done:", header["categories"], stats)
    return 0


def write_report(version, header, rows, spreads, default_metrics, solutions):
    L = [f"# Benchmark set {version}: generation report", "",
         f"Seed {header['seed']}, commit `{header['git_commit'][:10]}`, generated {header['generated_at']}, "
         f"{header['stats']['seconds']} s.", "",
         "Model files: " + ", ".join(f"`{f['path']}` ({f['status']}, `{f['sha256'][:12]}…`)" for f in header["model_files"]), "",
         f"Categories: {header['categories']}", "",
         "Rules: " + "; ".join(f"**{k}**: {v}" for k, v in header["rules"].items()), "",
         "Generation statistics: " + ", ".join(f"{k} {v}" for k, v in header["stats"].items()), "",
         "od_ts808 at its defaults (exclusion reference): " + ", ".join(f"{k} {v:.3g}" for k, v in default_metrics.items()), "",
         "## Metric spreads per chain (playable pool, meaningful values; 10 / 50 / 90 %; ✓ = eligible)", "",
         "| Chain | " + " | ".join(METRICS) + " |", "|---|" + "---|" * len(METRICS)]
    for chain, s in spreads.items():
        cells = [f"{s[n]['p10']:.3g} / {s[n]['p50']:.3g} / {s[n]['p90']:.3g} (n={s[n]['n']}) "
                 f"{'✓' if s[n]['eligible'] else '✗'}" for n in METRICS]
        L.append(f"| {' → '.join(chain)} | " + " | ".join(cells) + " |")
    L += ["", "Spread measure: dB metrics p90−p10 (needs ≥ 6 dB); thd/ac_peak_hz/out_pk log10(p90/p10) "
          "(needs ≥ 0.388 / 0.388 / 0.317 decades); even_odd p90−p10 ≥ 2 × window width at the median; n ≥ 20.", "",
          "## Targets", "",
          "| Id | Source | Cat. | Targets | Factor | Hit rate (at factor 1) | Start chain pass | "
          "Single blocks pass | Pool pass |", "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        ev = r["evidence"]
        tg = "; ".join(f"{t['name']} {'' if t['lo'] is None else f'{t['lo']:g}'}–{'' if t['hi'] is None else f'{t['hi']:g}'}"
                       for t in r["targets"])
        singles = ", ".join(f"{k} {v[1]}" for k, v in ev["single_blocks"].items())
        if "calibration" in r:
            c = r["calibration"]
            fac, hr = f"{c['factor']:g}{' (cap)' if c['capped'] else ''}", f"{c['hit_rate']:.3f} ({c['hit_rate_factor_1']:.3f})"
        elif r["source"] == "hand":
            fac, hr = "–", f"best chain {r['hit_rate_best_chain']:.3f}"
        else:
            fac, hr = "–", "0"
        L.append(f"| {r['id']} | {r['source']} | {r['category']} | {tg} | {fac} | {hr} | "
                 f"{ev['start_chain'][1]}/{ev['start_chain'][0]} | {singles} | {ev['pool_all'][1]}/{ev['pool_all'][0]} |")
    L += ["", "## Hand-written targets: hit rate per chain (passes / draws)", "",
          "| Id | " + " | ".join(next(iter(s["hit_rates_by_chain"] for s in solutions.values() if "hit_rates_by_chain" in s))) + " |"]
    L.append("|---|" + "---|" * 7)
    for tid, s in solutions.items():
        if "hit_rates_by_chain" in s:
            L.append(f"| {tid} | " + " | ".join(f"{v:.3f}" for v in s["hit_rates_by_chain"].values()) + " |")
    (OUT / f"{version}_report.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    sys.exit(main())
