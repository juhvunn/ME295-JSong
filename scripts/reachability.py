"""Stronger reachability check for the B/C labels of a benchmark set (docs/phase3_plan.md, section 1c).

Why: v1 labels came from 250 generator draws per chain. In batch S the fixed-topology agent (locked to
[od_ts808]) passed B and C targets with knobs at their end stops (drive = tone = 1.0), a corner the
draws rarely reach. Here, for every B and C target and every single block:
  1. corner grid: knobs {0, 0.5, 1} x every validated choice x parts {min, default, max}
  2. dense random samples (default 2000 per block): knobs uniform [0, 1] (the Validator's range),
     choices uniform over validated choices, parts uniform over the E-series values in [min, max]
  3. single-block designs simulated in benchmark runs (any method; real Checker results, read only)
  4. local search where 1-3 found no pass: deterministic pattern search on the Checker score from the
     3 best designs of that block (knob steps 0.2 -> 0.025, neighbouring choices and E-series values)
Every design is simulated once with the Checker and scored against all targets. Labels use the
generator's evidence rules: A = some od_ts808 design passes; B = none does, but the solution is a
single block or some other single block passes; C = no single block passes. Nothing in the benchmark
(windows, solutions, v1.yaml) is changed; the result goes to benchmarks/<v>_labels_check.yaml/.md.

Usage: python -m scripts.reachability --version v1 [--samples 2000] [--workers 2]
"""
import argparse
import itertools
import json
import math
import random
import time
from multiprocessing import Pool
from pathlib import Path

import yaml

from pedal_agent.build import load_block, parse_value
from pedal_agent.config import REPO_ROOT
from pedal_agent.validate import allowed_choices, block_ids, series_values
from scripts.make_benchmarks import START, passes, simulate

OUT = REPO_ROOT / "benchmarks"
SEED = 1117
GRID_KNOBS = (0.0, 0.5, 1.0)
STARTS = 3
SEARCH_SIMS = 100                    # per start
KNOB_STEPS = (0.2, 0.1, 0.05, 0.025)


def space(block_id: str) -> dict:
    """name -> ("pot", None) | ("choice", [..]) | ("part", [E-series values], default)."""
    _, meta = load_block(block_id)
    out = {}
    for name in sorted(meta["params"]):
        spec = meta["params"][name]
        if spec["type"] == "pot":
            out[name] = ("pot", None, spec["default"])
        elif spec["type"] == "choice":
            out[name] = ("choice", allowed_choices(spec, allow_unvalidated=False), spec["default"])
        else:
            vals = series_values(spec["series"], parse_value(spec["min"]), parse_value(spec["max"]))
            out[name] = ("part", vals, min(vals, key=lambda v: abs(math.log(v / parse_value(spec["value"])))))
    return out


def grid(block_id: str) -> list[dict]:
    sp = space(block_id)
    axes = []
    for name, (kind, vals, default) in sp.items():
        axes.append([(name, v) for v in (GRID_KNOBS if kind == "pot" else vals if kind == "choice"
                                          else sorted({vals[0], default, vals[-1]}))])
    return [dict(c) for c in itertools.product(*axes)]


def random_params(block_id: str, rng: random.Random) -> dict:
    return {name: round(rng.uniform(0, 1), 3) if kind == "pot" else rng.choice(vals)
            for name, (kind, vals, _) in space(block_id).items()}


def run_design(job):
    """(block_id, params) -> (block_id, params, metrics or None). None = DC check or simulation failure."""
    block_id, params = job
    rep = simulate([(block_id, params)])
    return block_id, params, (rep.metrics if rep.dc_ok and not rep.errors else None)


def score(metrics, targets) -> float:
    """Checker score (sum of relative distances outside the windows; 0 = pass)."""
    s = 0.0
    for t in targets:
        v = metrics[t["name"]]
        if t["lo"] is not None and v < t["lo"]:
            s += (t["lo"] - v) / max(abs(t["lo"]), 1e-9)
        elif t["hi"] is not None and v > t["hi"]:
            s += (v - t["hi"]) / max(abs(t["hi"]), 1e-9)
    return s


def neighbours(block_id: str, params: dict, step: float) -> list[dict]:
    out = []
    for name, (kind, vals, _) in space(block_id).items():
        cur = params[name]
        if kind == "pot":
            cand = [min(1.0, round(cur + step, 3)), max(0.0, round(cur - step, 3))]
        elif kind == "choice":
            cand = [v for v in vals if v != cur]
        else:
            i = min(range(len(vals)), key=lambda k: abs(math.log(vals[k] / cur)))
            cand = [vals[j] for j in (i - 1, i + 1) if 0 <= j < len(vals)]
        out += [{**params, name: v} for v in cand if v != cur]
    return out


def local_search(job):
    """Pattern search from one start on one block for one target; stops at the first pass.
    Returns (target_id, block_id, sims, passing params or None, best score, all simulated designs)."""
    tid, block_id, targets, start = job
    full = {name: default for name, (_, _, default) in space(block_id).items()}
    best_p = {**full, **start}
    _, _, m = run_design((block_id, best_p))
    best = score(m, targets) if m else math.inf
    seen, sims, tried = {json.dumps(best_p, sort_keys=True)}, 1, [(best_p, m)]
    if best == 0:
        return tid, block_id, sims, best_p, best, tried
    for step in KNOB_STEPS:
        improved = True
        while improved and sims < SEARCH_SIMS:
            improved = False
            for p in neighbours(block_id, best_p, step):
                key = json.dumps(p, sort_keys=True)
                if key in seen or sims >= SEARCH_SIMS:
                    continue
                seen.add(key)
                _, _, m = run_design((block_id, p))
                sims += 1
                tried.append((p, m))
                if m is None:
                    continue
                s = score(m, targets)
                if s < best:
                    best, best_p, improved = s, p, True
                    if s == 0:
                        return tid, block_id, sims, p, 0.0, tried
                    break                           # restart the neighbourhood from the new point
    return tid, block_id, sims, None, best, tried


def run_designs(root: Path) -> list[tuple[str, dict, dict, str]]:
    """Single-block designs simulated in benchmark runs: (block, params, metrics, run file)."""
    out = []
    for f in sorted(root.rglob("*.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        for s in r.get("steps", []):
            rep, cand = s.get("report"), s.get("candidate")
            if not rep or not cand or len(cand["chain"]) != 1 or not rep["dc_ok"] or rep["errors"] or not rep["metrics"]:
                continue
            out.append((cand["chain"][0]["block_id"], cand["chain"][0]["params"],
                        {k: float(v) for k, v in rep["metrics"].items()}, f"{f.parent.name}/{f.name}"))
    return out


def label(solution_chain: list[str], passing_blocks: set[str]) -> str:
    """The generator's evidence rules (scripts/make_benchmarks.py), applied to single-block evidence."""
    if tuple(solution_chain) == START or START[0] in passing_blocks:
        return "A"
    if len(solution_chain) == 1 or passing_blocks:
        return "B"
    return "C"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v1")
    ap.add_argument("--samples", type=int, default=2000, help="random samples per block")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--runs", default=None, help="benchmark run folder (default runs/bench/<version>)")
    args = ap.parse_args(argv)
    t0 = time.time()
    log = lambda *a: print(f"[{time.time() - t0:6.0f}s]", *a, flush=True)  # noqa: E731
    rows = yaml.safe_load((OUT / f"{args.version}.yaml").read_text(encoding="utf-8"))["targets"]
    sols = yaml.safe_load((OUT / f"{args.version}_solutions.yaml").read_text(encoding="utf-8"))
    todo = [r for r in rows if r["category"] in ("B", "C")]
    blocks = block_ids()
    rng = random.Random(SEED)

    # 1-2. grid + random samples, shared by all targets
    designs = [(b, p) for b in blocks for p in grid(b)]
    n_grid = len(designs)
    designs += [(b, random_params(b, rng)) for b in blocks for _ in range(args.samples)]
    log(f"{n_grid} grid + {len(designs) - n_grid} random designs over {blocks}, {args.workers} workers")
    with Pool(args.workers) as pool:
        sampled = []
        for i, d in enumerate(pool.imap(run_design, designs, chunksize=8), 1):
            sampled.append(d)
            if i % 500 == 0:
                log(f"  simulated {i}/{len(designs)}")
    valid = [(b, p, m, "grid" if i < n_grid else "random") for i, (b, p, m) in enumerate(sampled) if m]
    log(f"{len(valid)} of {len(sampled)} designs pass the DC checks")

    # 3. designs from benchmark runs
    from_runs = [(b, p, m, "run:" + src) for b, p, m, src in run_designs(Path(args.runs or REPO_ROOT / "runs" / "bench" / args.version))]
    log(f"{len(from_runs)} single-block designs from benchmark runs")
    evidence_pool = valid + from_runs

    result = {}
    for r in todo:
        ev = {}
        for b in blocks:
            mine = [(p, m, src) for bb, p, m, src in evidence_pool if bb == b]
            hits = [(p, src) for p, m, src in mine if passes(m, r["targets"])]
            ev[b] = {"designs": len(mine), "passes": len(hits),
                     "by_source": {k: sum(s.split(":")[0] == k for _, s in hits) for k in ("grid", "random", "run")},
                     "example": ({"params": hits[0][0], "source": hits[0][1]} if hits else None),
                     "search": None}
            ev[b]["_best"] = sorted(mine, key=lambda x: score(x[1], r["targets"]))[:STARTS]
        result[r["id"]] = ev

    # 4. local search where no pass was found
    jobs = [(tid, b, next(x for x in todo if x["id"] == tid)["targets"], p)
            for tid, ev in result.items() for b in blocks if ev[b]["passes"] == 0 for p, _, _ in ev[b]["_best"]]
    log(f"local search: {len(jobs)} starts (max {SEARCH_SIMS} sims each)")
    with Pool(args.workers) as pool:
        for tid, b, sims, p, best, _ in pool.imap_unordered(local_search, jobs):
            s = result[tid][b]["search"] or {"starts": 0, "sims": 0, "best_score": math.inf, "found": None}
            s["starts"] += 1
            s["sims"] += sims
            s["best_score"] = min(s["best_score"], best)
            if p is not None and s["found"] is None:
                s["found"] = p
            result[tid][b]["search"] = s
    log("local search done")

    out_rows = []
    for r in todo:
        ev = result[r["id"]]
        for b in blocks:
            ev[b].pop("_best")
            s = ev[b]["search"]
            if s:
                s["best_score"] = round(s["best_score"], 4) if math.isfinite(s["best_score"]) else "inf"
                if s["found"] and not ev[b]["example"]:
                    ev[b]["example"] = {"params": s["found"], "source": "local search"}
        passing = {b for b in blocks if ev[b]["passes"] > 0 or (ev[b]["search"] and ev[b]["search"]["found"])}
        sol_chain = [x["block_id"] for x in sols[r["id"]]["chain"]]
        out_rows.append({"id": r["id"], "source": r["source"], "old": r["category"],
                         "new": label(sol_chain, passing), "solution_chain": sol_chain,
                         "passing_single_blocks": sorted(passing), "evidence": ev})
        log(f"{r['id']}: {r['category']} -> {out_rows[-1]['new']}  passing single blocks {sorted(passing)}")

    header = {"version": args.version, "seed": SEED, "samples_per_block": args.samples, "grid_designs": n_grid,
              "valid_designs": len(valid), "run_designs": len(from_runs), "search_starts": len(jobs),
              "search_sims_max_per_start": SEARCH_SIMS, "seconds": round(time.time() - t0),
              "note": "analysis only; v1.yaml categories, windows and solutions unchanged"}
    path = OUT / f"{args.version}_labels_check.yaml"
    path.write_text(yaml.safe_dump({"header": header, "targets": {x["id"]: x for x in out_rows}},
                                   sort_keys=False, allow_unicode=True), encoding="utf-8")
    log(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
