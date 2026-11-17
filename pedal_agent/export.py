"""Export an accepted design: exports/<run_id>/{netlist.cir, bom.csv, summary.md}.

Only for runs the human accepted; the exported design is the run's best step (the one shown for review).
netlist.cir is the exact netlist the Checker simulated: it is rebuilt from the candidate and must match the
SHA-256 recorded in that step's CheckReport, otherwise the export is refused (blocks or models changed since).
bom.csv lists the parts of the simulated signal path, read from the rendered block subcircuits.
An existing export is never overwritten.

    python -m pedal_agent.export <run_id> [--runs-dir DIR]
"""
import argparse
import csv
import hashlib
import io
import re
from pathlib import Path

from pedal_agent.build import load_block, parse_value, render, taper
from pedal_agent.checker import build_netlist
from pedal_agent.graph import RunStore
from pedal_agent.harness import LOAD, PICKUP, VCC
from pedal_agent.schemas import BlockInstance, RunRecord

KIND = {"R": "resistor", "C": "capacitor", "L": "inductor", "D": "diode", "Q": "transistor", "X": "op-amp"}
UNIT = {"R": "Ω", "C": "F", "L": "H"}
BOM_COLUMNS = ["block_pos", "block_id", "designator", "kind", "value", "setting", "spice_model", "note"]


class NotExportable(RuntimeError):
    """The run is not accepted, has no simulated best step, or its netlist cannot be reproduced."""


def exports_dir(store: RunStore) -> Path:
    return store.dir.parent / "exports"             # runs/ -> exports/ next to it (gitignored)


def eng(x: float, unit: str = "") -> str:
    """4.7e-08 -> '47n', 1500000 -> '1.5Meg' (SPICE-style suffixes)."""
    for suf, f in (("Meg", 1e6), ("k", 1e3), ("", 1.0), ("m", 1e-3), ("u", 1e-6), ("n", 1e-9), ("p", 1e-12)):
        if abs(x) >= f * 0.9995:
            return f"{x / f:.3g}{suf}{unit}"
    return f"{x:.3g}{unit}"


def same(a, b) -> bool:
    """Equal part values ('47n' vs 4.7e-08), up to float rounding."""
    x, y = parse_value(a), parse_value(b)
    return abs(x - y) <= 1e-9 * max(abs(x), abs(y))


def is_default(p: dict, v) -> bool:
    d = p.get("default", p.get("value"))
    return same(v, d) if p["type"] in ("component", "pot") else v == d


def show(p: dict, v) -> str:
    """A parameter value as in block.yaml (components in SPICE notation, e.g. 47n)."""
    return eng(parse_value(v)) if p["type"] == "component" else str(v)


def _elements(subckt: str) -> list[tuple[str, list[str]]]:
    """(designator, tokens) of the element lines between .subckt and .ends."""
    out = []
    for line in subckt.splitlines():
        line = line.split(";")[0].strip()
        if line and line[0] in KIND:
            tok = line.split()
            out.append((tok[0], tok))
    return out


def bom_rows(pos: int, blk: BlockInstance) -> list[dict]:
    """BOM rows of one block, in template order. Pots appear once (not as their A/B halves)."""
    _, meta = load_block(blk.block_id)
    vals = {k: p.get("default", p.get("value")) for k, p in meta["params"].items()} | blk.params
    pots = {p["designator"]: (name, p) for name, p in meta["params"].items() if p["type"] == "pot"}
    comps = {name: p for name, p in meta["params"].items() if p["type"] == "component"}
    choice_of = {d: name for name, p in meta["params"].items() if p["type"] == "choice" for d in p["designators"]}
    rows, seen_pots = [], set()
    for des, tok in _elements(render(blk.block_id, blk.params)):
        row = {"block_pos": pos, "block_id": blk.block_id, "designator": des, "kind": KIND[des[0]],
               "value": "", "setting": "", "spice_model": "", "note": ""}
        pot = des if des in pots else des[:-1] if des[-1] in "AB" and des[:-1] in pots else None
        if pot:
            if pot in seen_pots:
                continue
            seen_pots.add(pot)
            name, p = pots[pot]
            x = float(vals[name])
            rt = parse_value(p["r_total"])
            f = taper(1.0 - x if p.get("invert") else x, p["taper"])
            split = f"{eng(rt * f, 'Ω')}" if p["mode"] == "rheostat" else \
                f"A {eng(rt * f, 'Ω')} / B {eng(rt * (1 - f), 'Ω')}"
            row.update(designator=pot, kind=f"pot ({p['taper']}, {p['mode']})", value=eng(rt, "Ω"),
                       setting=f"{name} = {x:g} ({split})")
        elif des[0] in UNIT:
            row["value"] = eng(parse_value(tok[3]), UNIT[des[0]])
            if des in comps:
                default = comps[des]["value"]
                row["note"] = "default" if same(vals[des], default) else f"agent-set (default {default})"
        else:
            row["spice_model"] = tok[-1] if des[0] == "X" else tok[3] if des[0] == "D" else tok[4]
            if des[0] == "X":
                row["note"] = "one op-amp section (subcircuit)"
        if des in choice_of:
            row["setting"] = f"{choice_of[des]} = {vals[choice_of[des]]}"
        rows.append(row)
    return rows


def _excluded(block_id: str) -> str:
    d, meta = load_block(block_id)
    text = (d / meta["template"]).read_text(encoding="utf-8")
    m = re.search(r"(?m)^\*\s*Excluded:\s*(.+)$", text)
    return m.group(1).strip() if m else "not stated"


def summary_md(run: RunRecord, sha: str, project_name: str | None) -> str:
    step = run.best
    rep = step.report
    measured = {r.name: r for r in rep.results}
    L = [f"# Exported design: {project_name or run.project_id}", "",
         f"- Run: `{run.run_id}` (status {run.status}), exported design = step {step.n} of {len(run.steps)}",
         f"- Goal: {run.spec.goal_text}",
         f"- Model: {run.model_id} (effort {run.effort}); code commit {run.code_commit or 'not recorded'}",
         f"- Simulations used: {run.sims_used} of {run.sim_budget}; LLM tokens {run.input_tokens:,} in / "
         f"{run.output_tokens:,} out (API-equivalent ${run.api_equivalent_cost_usd:.2f})",
         f"- netlist.cir SHA-256: `{sha}` (matches the Checker report of step {step.n})", ""]
    if rep.placeholder_or_unvalidated:
        L += ["> **Warning: this design was simulated with a placeholder or unvalidated model "
              f"({', '.join(rep.unvalidated_choices) or 'see model files'}). Do not use it for reported results.**", ""]
    L += ["## Signal chain", "",
          f"Pickup model (R {PICKUP['R']}, L {PICKUP['L']} H, cable {PICKUP['C_cable']}F) → "
          + " → ".join(f"{i}. `{b.block_id}`" for i, b in enumerate(run.best.candidate.chain, start=1))
          + f" → {LOAD} load (amp input). Supply {VCC:g} V.", ""]
    for i, b in enumerate(step.candidate.chain, start=1):
        _, meta = load_block(b.block_id)
        vals = {k: p.get("default", p.get("value")) for k, p in meta["params"].items()} | b.params
        L.append(f"{i}. **{meta['name']}** (`{b.block_id}`): "
                 + ", ".join(f"{k} = {show(p, vals[k])}" + (" (default)" if is_default(p, vals[k]) else "")
                             for k, p in meta["params"].items()))
    L += ["", "## Targets (approved spec) and simulated result", "",
          "| Target | Metric | Range | Simulated | Status |", "|---|---|---|---|---|"]
    for t in run.spec.targets:
        r = measured.get(t.name)
        rng = f"{'−∞' if t.lo is None else f'{t.lo:g}'} … {'∞' if t.hi is None else f'{t.hi:g}'} {t.unit}".strip()
        L.append(f"| {t.label} | `{t.name}` | {rng} | {f'{r.value:.3g} {t.unit}'.strip() if r else '–'} | {r.status if r else '–'} |")
    L += ["", f"Score {rep.score:.3g} (0 = every target met). DC bias checks: "
          + ("all within range." if rep.dc_ok else "; ".join(rep.errors)),
          f"Test signal: {run.spec.test_signal['f0_hz']:g} Hz sine, {run.spec.test_signal['amp_v']:g} V EMF "
          "into the pickup model.", "",
          "## Model files", ""]
    L += [f"- `{f.path}` ({f.status}), SHA-256 `{f.sha256[:16]}…`" for f in rep.model_files]
    L += ["", "## Files", "",
          "- `netlist.cir`: the exact ngspice netlist simulated (pickup model, blocks, 1 MΩ load, analyses).",
          "- `bom.csv`: parts of the simulated signal path, per block; pots with their knob setting.", "",
          "## Not included", ""]
    L += [f"- `{b.block_id}`: {_excluded(b.block_id)}" for b in step.candidate.chain]
    L += ["- Power supply filtering and protection, enclosure, wiring.", "",
          "This design was only simulated (preamp/overdrive path, ngspice, fitted models). It was not built "
          "or listened to. Component tolerances and real-part variation are not modelled.", ""]
    return "\n".join(L)


def export_run(run_id: str, store: RunStore | None = None, project_name: str | None = None) -> Path:
    """Write exports/<run_id>/ for an accepted run; returns the folder. Never overwrites."""
    store = store or RunStore()
    run = store.load(run_id)
    if run.status != "accepted":
        raise NotExportable(f"run {run_id} is {run.status}; only accepted designs are exported")
    step = run.best
    if step is None or step.report is None or not step.report.netlist_sha256:
        raise NotExportable(f"run {run_id} has no simulated design to export")
    net, _ = build_netlist(step.candidate, run.spec.test_signal["f0_hz"], run.spec.test_signal["amp_v"])
    sha = hashlib.sha256(net.encode()).hexdigest()
    if sha != step.report.netlist_sha256:
        raise NotExportable(f"the netlist rebuilt today differs from the one simulated in step {step.n} "
                            "(blocks or models changed since the run); not exported")
    out = exports_dir(store) / run_id
    if out.exists():
        raise FileExistsError(f"{out} already exists; not overwritten")
    rows = [r for i, b in enumerate(step.candidate.chain, start=1) for r in bom_rows(i, b)]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=BOM_COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    out.mkdir(parents=True)
    (out / "netlist.cir").write_bytes(net.encode())                      # byte-identical to the simulated text
    (out / "bom.csv").write_text(buf.getvalue(), encoding="utf-8-sig", newline="")   # BOM so Excel reads Ω
    (out / "summary.md").write_text(summary_md(run, sha, project_name), encoding="utf-8", newline="\n")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pedal_agent.export", description=__doc__.splitlines()[0])
    ap.add_argument("run_id")
    ap.add_argument("--runs-dir")
    args = ap.parse_args(argv)
    try:
        print(export_run(args.run_id, RunStore(args.runs_dir)))
    except (NotExportable, FileExistsError) as e:
        print(f"not exported: {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
