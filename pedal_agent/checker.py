"""Deterministic Checker: simulate a candidate chain (1-3 blocks), compute metrics, judge vs targets."""
import hashlib, os, re
from pathlib import Path
import numpy as np
from pedal_agent.build import render, load_block
from pedal_agent.config import REPO_ROOT, load_config
from pedal_agent.harness import netlist
from pedal_agent.provenance import describe, flagged, unvalidated_choices
from pedal_agent.schemas import Candidate, CheckReport, MetricResult, Plots, TargetSpec
from pedal_agent.tools.simulate import simulate as run_ngspice

# Overrides (for scripts/tests): MODELS = one model file for everything (also the MODELS env var);
# MODEL_SET = a set name from config.yaml models.sets. Default: config.yaml models.set.
MODELS = os.environ.get("MODELS")
MODEL_SET = None

def _defined_names(paths):
    names = set()
    for p in paths:
        names |= {m.lower() for m in re.findall(r"(?im)^\.(?:model|subckt)\s+(\S+)", p.read_text(encoding="utf-8"))}
    return names

def model_paths(cand: Candidate | None = None) -> list[Path]:
    """Model library files pasted into the netlist (each recorded in the CheckReport).
    The unvalidated-extra file is added only when the candidate uses an unvalidated choice
    and the set does not already define its models."""
    if MODELS:
        return [Path(MODELS)]
    cfg = load_config()["models"]
    paths = [REPO_ROOT / p for p in cfg["sets"][MODEL_SET or cfg["set"]]]
    if cand is not None and unvalidated_choices(cand):
        extra = REPO_ROOT / cfg["unvalidated_extra"]
        if not _defined_names([extra]) <= _defined_names(paths):
            paths.append(extra)
    return paths

def models_text(cand: Candidate | None = None):
    return "\n".join(p.read_text(encoding="utf-8") for p in model_paths(cand))

def provenance(cand: Candidate) -> dict:
    files = [describe(p) for p in model_paths(cand)]
    unval = unvalidated_choices(cand)
    return {"model_files": files, "unvalidated_choices": unval,
            "placeholder_or_unvalidated": flagged(files, unval)}

def _harmonics(t, v, f0, n=10):
    v = v - v.mean(); N = len(t)
    tt = np.linspace(t[0], t[-1], N); vv = np.interp(tt, t, v) * np.hanning(N)
    sp = np.abs(np.fft.rfft(vv)); f = np.fft.rfftfreq(N, tt[1] - tt[0])
    return np.array([sp[np.argmin(abs(f - k * f0))] for k in range(1, n + 1)])

def distortion(t, v, f0):
    """(thd_pct, even_odd) of waveform v(t) at fundamental f0, harmonics 2-10."""
    h = _harmonics(t, v, f0)
    odd = np.sqrt((h[2::2] ** 2).sum())
    return (float(100 * np.sqrt((h[1:] ** 2).sum()) / h[0]),
            float(np.sqrt((h[1::2] ** 2).sum()) / odd) if odd > 0 else 0.0)

# Measured THD floor of distortion() for a pure sine / linear chain (1.13e-4 to 1.23e-4 %, Hann-window
# leakage of the 20 ms window; tests/test_checker_floor.py). Below ~10x this, thd_pct and even_odd are noise.
THD_FLOOR_PCT = 1.3e-4

# AC and transient analyses shared by check() and the noise-floor measurement (tests/test_checker_floor.py)
ANALYSES = ["ac dec 50 20 20k", "wrdata ac.txt vdb(out)", "tran 5u 60m 40m", "wrdata tran.txt v(emf) v(out)"]

def build_netlist(cand: Candidate, f0=1000.0, amp=0.3):
    """(netlist text, probes) exactly as simulate() runs it; also used by export.py."""
    blocks, probes = [], []   # probes: (label, vector, expect)
    for i, blk in enumerate(cand.chain, start=1):
        _, meta = load_block(blk.block_id)
        blocks.append((render(blk.block_id, blk.params), meta["subckt"]))
        prefix = f"{blk.block_id}." if len(cand.chain) > 1 else ""
        probes += [(prefix + name, f"v(x{i}.{c['node']})", c["expect"])
                   for name, c in meta.get("dc_checks", {}).items()]
    ctrl = "\n".join(["op", f"wrdata op.txt {' '.join(v for _, v, _ in probes) or 'v(out)'}", *ANALYSES])
    return netlist(blocks, models_text(cand), amp, f0, ctrl), probes

def simulate(cand: Candidate, f0=1000.0, amp=0.3):
    """One netlist for the whole chain; DC checks of block i are probed as v(x<i>.<node>)."""
    net, probes = build_netlist(cand, f0, amp)
    sha = hashlib.sha256(net.encode()).hexdigest()
    r = run_ngspice(net)  # sandboxed: directive filter, timeout, runs/<id>/ + logs/<id>.log
    out = {f: np.loadtxt(r.run_dir / f"{f}.txt") for f in ("op", "ac", "tran") if (r.run_dir / f"{f}.txt").exists()}
    return probes, out, sha, r

def check(cand: Candidate, spec: TargetSpec) -> CheckReport:
    f0, amp = spec.test_signal["f0_hz"], spec.test_signal["amp_v"]
    prov = provenance(cand)
    probes, out, sha, r = simulate(cand, f0, amp)
    if not all(k in out for k in ("op", "ac", "tran")):
        return CheckReport(metrics={}, results=[], score=float("inf"), dc_ok=False,
                           errors=[f"ngspice failed (returncode={r.returncode}, timed_out={r.timed_out}); see {r.log_path}"], netlist_sha256=sha, **prov)
    # DC sanity
    dc = np.atleast_2d(out["op"])[0, 1::2]
    errors = [f"DC {label}={v:.2f} V outside {expect}"
              for (label, _, expect), v in zip(probes, dc) if not expect[0] <= v <= expect[1]]
    ac, tr = out["ac"], out["tran"]
    i = ac[:, 1].argmax()
    thd, eo = distortion(tr[:, 0], tr[:, 3], f0)
    m = {"gain_1k_db": float(np.interp(1000.0, ac[:, 0], ac[:, 1])),
         "ac_peak_db": float(ac[i, 1]), "ac_peak_hz": float(ac[i, 0]),
         "thd_pct": thd, "even_odd": eo,
         "out_pk_v": float(np.abs(tr[:, 3] - tr[:, 3].mean()).max())}
    results, score = [], 0.0
    for tg in spec.targets:
        v = m[tg.name]
        if tg.lo is not None and v < tg.lo:
            st, err = "low", (tg.lo - v) / max(abs(tg.lo), 1e-9)
        elif tg.hi is not None and v > tg.hi:
            st, err = "high", (v - tg.hi) / max(abs(tg.hi), 1e-9)
        else:
            st, err = "pass", 0.0
        results.append(MetricResult(name=tg.name, value=v, status=st)); score += tg.weight * err
    # last 2 periods for the waveform plot, every other AC point
    keep = tr[:, 0] >= tr[-1, 0] - 2 / f0
    plots = Plots(t_s=tr[keep, 0][::4].tolist(), v_in=tr[keep, 1][::4].tolist(), v_out=tr[keep, 3][::4].tolist(),
                  freq_hz=ac[::2, 0].tolist(), mag_db=ac[::2, 1].tolist())
    return CheckReport(metrics=m, results=results, score=score, dc_ok=not errors,
                       errors=errors, netlist_sha256=sha, plots=plots, **prov)
