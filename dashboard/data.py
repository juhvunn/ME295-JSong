"""Read-only data layer for the dashboard (docs/DASHBOARD_SPEC.md, section 1).

Only reads RunRecord files (runs/*.json, runs/bench/**) and the block library; never simulates and never
writes. Every panel's content comes from a plain function here, so it can be tested without Streamlit.
"""
import json
import re
import shutil
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path

from pedal_agent.build import load_block, parse_value, render
from pedal_agent.config import REPO_ROOT, load_config
from pedal_agent.harness import LOAD, PICKUP
from pedal_agent.schemas import TOPOLOGY_ACTIONS, RunRecord, Step

STATUS_TEXT = {"awaiting_spec_approval": "waiting for spec approval", "running": "running",
               "awaiting_feedback": "waiting for feedback", "accepted": "design accepted", "stopped": "stopped"}
RESULT_TEXT = {"pass": "Pass", "low": "Too low", "high": "Too high"}
KIND = {"R": "Resistor", "C": "Capacitor", "L": "Inductor", "D": "Diode", "Q": "Transistor", "X": "Op-amp"}
CATEGORY_ORDER = ("overdrive", "distortion", "fuzz")


# ---------- runs ----------
def run_files(root: Path | None = None) -> list[Path]:
    import os
    root = root or REPO_ROOT / load_config()["paths"]["runs_dir"]
    files = []
    for d, subdirs, names in os.walk(root):
        subdirs[:] = [s for s in subdirs if s != "sims"]       # ngspice scratch: thousands of folders, no runs
        files += [Path(d) / n for n in names if n.endswith(".json")]
    return sorted(files)


def _best(d: dict) -> dict | None:
    return next((s for s in d.get("steps", []) if s["n"] == d.get("best_step")), None)


def index_entry(path: Path) -> dict | None:
    """One 'Saved circuits' row from the raw JSON (fast: no model validation)."""
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if "run_id" not in d or "steps" not in d:
        return None
    best = _best(d)
    results = (best or {}).get("report", {}) or {}
    results = results.get("results", [])
    chain = [b["block_id"] for b in ((best or {}).get("candidate") or {}).get("chain", [])]
    bench = d.get("benchmark")
    spec = d.get("spec") or {}
    if bench:
        name = f"{bench['set']} {bench['target_id']} · {d['mode']} · seed {d.get('seed')}"
    else:
        name = d.get("project_id", d["run_id"])
    return {"path": str(path), "run_id": d["run_id"], "name": name, "mode": d.get("mode", "agent"),
            "model_id": d.get("model_id"), "status": d.get("status"), "stop_reason": d.get("stop_reason"),
            "set": bench["set"] if bench else None, "target_id": bench["target_id"] if bench else None,
            "category": bench["category"] if bench else None, "seed": d.get("seed"),
            "chain": " → ".join(chain) or "–", "n_pass": sum(r["status"] == "pass" for r in results),
            "n_targets": len(spec.get("targets", [])), "sims_used": d.get("sims_used", 0),
            "goal_text": spec.get("goal_text", ""),
            "spec_key": json.dumps([spec.get("goal_text"), spec.get("targets")], sort_keys=True),
            "created_at": d.get("created_at", "")}


def build_index(root: Path | None = None, cache: Path | None = None) -> list[dict]:
    """Index of all runs. With cache (a JSON file outside runs/, e.g. results/dashboard_index.json), only
    files whose size or modification time changed are re-read (benchmark runs are ~160 kB each)."""
    old = {}
    if cache and cache.exists():
        try:
            old = json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            old = {}
    new, entries = {}, []
    for p in run_files(root):
        st = p.stat()
        key, stamp = str(p), [st.st_size, st.st_mtime_ns]
        hit = old.get(key)
        e = hit["entry"] if hit and hit["stamp"] == stamp else index_entry(p)
        new[key] = {"stamp": stamp, "entry": e}
        if e:
            entries.append(e)
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(new), encoding="utf-8")
    return entries


def load_run(path: str | Path) -> RunRecord:
    return RunRecord.model_validate_json(Path(path).read_text(encoding="utf-8"))


def simulated_steps(run: RunRecord) -> list[Step]:
    return [s for s in run.steps if s.report is not None and s.candidate is not None]


def display_step(run: RunRecord, n: int | None = None) -> Step | None:
    """The step shown in the centre column: step n, else the best step, else the last simulated one."""
    steps = simulated_steps(run)
    if n is not None:
        return next((s for s in steps if s.n == n), None)
    return run.best if run.best and run.best.report else (steps[-1] if steps else None)


def header(run: RunRecord, step: Step | None) -> dict:
    n_t = len(run.spec.targets) if run.spec else 0
    n_p = step.report.n_pass if step and step.report else 0
    state = STATUS_TEXT.get(run.status, run.status)
    if run.status == "stopped" and run.stop_reason:
        state = f"stopped ({run.stop_reason.replace('_', ' ')})"
    return {"name": run.benchmark and f"Benchmark {run.benchmark.set} · {run.benchmark.target_id}" or run.project_id,
            "goal": run.spec.goal_text if run.spec else "", "badge": f"{n_p} of {n_t} targets met - {state}",
            "n_pass": n_p, "n_targets": n_t, "flagged": bool(run.placeholder_or_unvalidated),
            "model_id": run.model_id, "mode": run.mode}


# ---------- signal chain and components ----------
def pickup_text() -> str:
    return f"Guitar pickup ({PICKUP['R']}, {PICKUP['L']} H)"


def amp_text() -> str:
    return f"Amp input ({LOAD.replace('Meg', ' MΩ')})"


def full_params(block_id: str, params: dict) -> dict:
    _, meta = load_block(block_id)
    vals = {k: p.get("default", p.get("value")) for k, p in meta["params"].items()}
    vals.update(params or {})
    return vals


def chain_cards(step: Step) -> list[dict]:
    """One card per block: name and all settings (knobs as 0-1 positions), changed ones marked."""
    cards = []
    for b in step.candidate.chain:
        _, meta = load_block(b.block_id)
        vals = full_params(b.block_id, b.params)
        cards.append({"block_id": b.block_id, "name": meta["name"], "category": meta["category"],
                      "settings": [{"name": k, "value": v, "type": meta["params"][k]["type"],
                                    "changed": k in (b.params or {})} for k, v in vals.items()]})
    return cards


def eng(x: float, unit: str = "") -> str:
    for f, s in ((1e6, "M"), (1e3, "k"), (1, ""), (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"), (1e-12, "p")):
        if abs(x) >= f:
            return f"{x / f:.3g} {s}{unit}"
    return f"{x:.3g} {unit}"


def _adjustable(meta: dict) -> dict[str, str]:
    """Netlist element base name -> parameter name."""
    out = {}
    for name, p in meta["params"].items():
        if p["type"] == "pot":
            out[p["designator"]] = name
        elif p["type"] == "choice":
            for d in p.get("designators", []):
                out[d] = name
        else:
            out[name] = name
    return out


def components(block_id: str, params: dict) -> list[dict]:
    """Component list from the generated circuit text (the same text the Checker simulated)."""
    _, meta = load_block(block_id)
    adj = _adjustable(meta)
    unit = {"R": "Ω", "C": "F", "L": "H"}
    rows = []
    for line in render(block_id, params).splitlines():
        line = line.strip()
        if not line or line[0] not in KIND:
            continue
        body, _, comment = line.partition(";")
        tok = body.split()
        des, kind = tok[0], KIND[line[0]]
        base = re.sub(r"[AB]$", "", des) if re.sub(r"[AB]$", "", des) in adj and des not in adj else des
        if kind in ("Resistor", "Capacitor", "Inductor"):
            value = eng(parse_value(tok[3]), unit[line[0]])
        else:
            value = tok[-1]                                    # model name
        rows.append({"designator": des, "kind": kind, "value": value, "note": comment.strip(),
                     "parameter": adj.get(base, ""), "adjustable": base in adj})
    return rows


# ---------- panels ----------
def design_choices(run: RunRecord) -> list[dict]:
    rows = []
    for s in run.steps:
        if s.validation_errors:
            tag = "rejected"
        elif s.duplicate_of is not None:
            tag = "duplicate"
        elif s.action in TOPOLOGY_ACTIONS:
            tag = "topology"
        elif s.action == "adjust_params":
            tag = "values"
        else:
            tag = s.agent
        rows.append({"n": s.n, "action": s.action, "tag": tag, "title": s.title, "why": s.why,
                     "simulated": s.report is not None, "n_pass": s.report.n_pass if s.report else None,
                     "errors": s.validation_errors})
    return rows


def target_rows(run: RunRecord, step: Step | None) -> list[dict]:
    measured = {r.name: r for r in (step.report.results if step and step.report else [])}
    rows = []
    for t in (run.spec.targets if run.spec else []):
        lo = "" if t.lo is None else f"{t.lo:g}"
        hi = "" if t.hi is None else f"{t.hi:g}"
        rng = f"{lo} – {hi}" if lo and hi else (f"≥ {lo}" if lo else f"≤ {hi}")
        r = measured.get(t.name)
        rows.append({"target": t.label, "metric": t.name, "range": f"{rng} {t.unit}".strip(),
                     "measured": f"{r.value:.3g} {t.unit}".strip() if r else "–",
                     "status": RESULT_TEXT[r.status] if r else "Not measured"})
    return rows


def agent_panel(run: RunRecord) -> dict:
    return {"iterations": len(run.steps), "sims": f"{run.sims_used} / {run.sim_budget}",
            "topology_changes": run.topology_changes, "stop_reason": run.stop_reason or "–",
            "planner_calls": sum(s.agent == "planner" for s in run.steps),
            "tokens": f"{run.input_tokens} in / {run.output_tokens} out", "cost": f"${run.cost_usd:.2f}",
            "model": f"{run.model_id} ({run.effort})", "mode": run.mode, "seed": run.seed,
            "benchmark": run.benchmark and {"set": run.benchmark.set, "target": run.benchmark.target_id,
                                           "category": run.benchmark.category}}


def repeated_runs(index: list[dict], entry: dict) -> dict | None:
    """Runs of the same spec and mode: success rate and median sims (None if only one run)."""
    same = [e for e in index if e["spec_key"] == entry["spec_key"] and e["mode"] == entry["mode"]
            and e["stop_reason"] is not None]
    if len(same) < 2:
        return None
    ok = [e["sims_used"] for e in same if e["stop_reason"] == "all_pass"]
    return {"runs": len(same), "successes": len(ok), "success_rate": len(ok) / len(same),
            "median_sims_to_success": statistics.median(ok) if ok else None,
            "median_sims_used": statistics.median(e["sims_used"] for e in same)}


def library() -> dict[str, list[dict]]:
    """Reference models grouped by category."""
    groups = defaultdict(list)
    for d in sorted((REPO_ROOT / "blocks").iterdir()):
        if not (d / "block.yaml").exists():
            continue
        _, meta = load_block(d.name)
        src = meta.get("source", {})
        short = (src.get("schematic", "") if isinstance(src, dict) else str(src)).split(",")[0]
        groups[meta["category"]].append({
            "block_id": meta["id"], "name": meta["name"],
            "character": re.split(r"(?<=\.)\s", " ".join(meta.get("character", "").split()), maxsplit=1)[0],
            "source": re.sub(r"\s+schematic$", "", short.strip()), "url": src.get("url") if isinstance(src, dict) else None,
            "params": list(meta["params"])})
    return {c: groups[c] for c in sorted(groups, key=lambda c: (CATEGORY_ORDER + (c,)).index(c))}


def ngspice_version() -> str:
    exe = load_config()["ngspice"]["executable"]
    if not shutil.which(exe):
        return "ngspice (not found)"
    try:
        out = subprocess.run([exe, "-v"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return "ngspice"
    m = re.search(r"ngspice-(\d+)", out)
    return f"ngspice {m.group(1)}" if m else "ngspice"
