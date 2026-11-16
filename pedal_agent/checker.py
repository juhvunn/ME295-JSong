"""Deterministic Checker: simulate a candidate chain, compute metrics, judge vs targets.
Phase-1 version: single-block chains (multi-block chains in Phase 2)."""
import hashlib, os
from pathlib import Path
import numpy as np
from pedal_agent.build import render, load_block
from pedal_agent.config import REPO_ROOT
from pedal_agent.harness import netlist
from pedal_agent.schemas import Candidate, CheckReport, MetricResult, Plots, TargetSpec
from pedal_agent.tools.simulate import simulate as run_ngspice

MODELS = os.environ.get("MODELS", str(REPO_ROOT / "models" / "smoke_models.lib"))

def models_text():
    return Path(MODELS).read_text(encoding="utf-8")

def _harmonics(t, v, f0, n=10):
    v = v - v.mean(); N = len(t)
    tt = np.linspace(t[0], t[-1], N); vv = np.interp(tt, t, v) * np.hanning(N)
    sp = np.abs(np.fft.rfft(vv)); f = np.fft.rfftfreq(N, tt[1] - tt[0])
    return np.array([sp[np.argmin(abs(f - k * f0))] for k in range(1, n + 1)])

def simulate(cand: Candidate, f0=1000.0, amp=0.3):
    if len(cand.chain) != 1:
        raise NotImplementedError("multi-block chains: Phase 2")
    blk = cand.chain[0]
    _, meta = load_block(blk.block_id)
    nodes = [c["node"] for c in meta.get("dc_checks", {}).values()]
    ctrl = "\n".join(["op", f"wrdata op.txt {' '.join(f'v(x1.{n})' for n in nodes) or 'v(out)'}",
                      "ac dec 50 20 20k", "wrdata ac.txt vdb(out)",
                      "tran 5u 60m 40m", "wrdata tran.txt v(emf) v(out)"])
    net = netlist(render(blk.block_id, blk.params), meta["subckt"], models_text(), amp, f0, ctrl)
    sha = hashlib.sha256(net.encode()).hexdigest()
    r = run_ngspice(net)  # sandboxed: directive filter, timeout, runs/<id>/ + logs/<id>.log
    out = {f: np.loadtxt(r.run_dir / f"{f}.txt") for f in ("op", "ac", "tran") if (r.run_dir / f"{f}.txt").exists()}
    return meta, nodes, out, sha, r

def check(cand: Candidate, spec: TargetSpec) -> CheckReport:
    f0, amp = spec.test_signal["f0_hz"], spec.test_signal["amp_v"]
    meta, nodes, out, sha, r = simulate(cand, f0, amp)
    if not all(k in out for k in ("op", "ac", "tran")):
        return CheckReport(metrics={}, results=[], score=float("inf"), dc_ok=False,
                           errors=[f"ngspice failed (returncode={r.returncode}, timed_out={r.timed_out}); see {r.log_path}"], netlist_sha256=sha)
    # DC sanity
    dc = dict(zip(nodes, np.atleast_2d(out["op"])[0, 1::2]))
    errors = [f"DC {n}={dc[c['node']]:.2f} V outside {c['expect']}"
              for n, c in meta.get("dc_checks", {}).items()
              if not c["expect"][0] <= dc[c["node"]] <= c["expect"][1]]
    ac, tr = out["ac"], out["tran"]
    i = ac[:, 1].argmax()
    h = _harmonics(tr[:, 0], tr[:, 3], f0)
    odd = np.sqrt((h[2::2] ** 2).sum())
    m = {"gain_1k_db": float(np.interp(1000.0, ac[:, 0], ac[:, 1])),
         "ac_peak_db": float(ac[i, 1]), "ac_peak_hz": float(ac[i, 0]),
         "thd_pct": float(100 * np.sqrt((h[1:] ** 2).sum()) / h[0]),
         "even_odd": float(np.sqrt((h[1::2] ** 2).sum()) / odd) if odd > 0 else 0.0,
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
                       errors=errors, netlist_sha256=sha, plots=plots)
