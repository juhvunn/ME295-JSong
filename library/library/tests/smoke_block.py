"""Smoke test for any library block.
Usage: python tests/smoke_block.py <block_id> [<block_id> ...]
Runs DC checks, AC response and 1 kHz THD for every D_clip / Q_model choice.
Uses placeholder models unless the MODELS env var points to real ones."""
import os, sys, subprocess, tempfile
from pathlib import Path
import numpy as np
LIB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LIB))
from build import render, load_block
from harness import netlist

MODELS = os.environ.get("MODELS", str(LIB / "models" / "smoke_models.lib"))
F0 = 1000.0
AMPS = (0.05, 0.5)      # pickup EMF peak (V)

def simulate(block_id, overrides, amp, dc_nodes):
    _, meta = load_block(block_id)
    probes = " ".join(f"v(x1.{n})" for n in dc_nodes)
    ctrl = f"""op
wrdata op.txt {probes}
ac dec 50 20 20k
wrdata ac.txt vdb(out)
tran 5u 60m 40m
wrdata tran.txt v(out)"""
    net = netlist(render(block_id, overrides), meta["subckt"], MODELS, amp, F0, ctrl)
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "c.cir").write_text(net)
        r = subprocess.run(["ngspice", "-b", "c.cir"], cwd=td, capture_output=True,
                           text=True, timeout=300)
        res = {}
        for f in ("op", "ac", "tran"):
            fp = Path(td) / f"{f}.txt"
            if fp.exists():
                res[f] = np.loadtxt(fp)
    return r, res

def harmonics(t, v, n=10):
    v = v - v.mean(); N = len(t)
    tt = np.linspace(t[0], t[-1], N); vv = np.interp(tt, t, v) * np.hanning(N)
    sp = np.abs(np.fft.rfft(vv)); f = np.fft.rfftfreq(N, tt[1] - tt[0])
    return np.array([sp[np.argmin(abs(f - k * F0))] for k in range(1, n + 1)])

def metrics(res):
    ac, tr = res["ac"], res["tran"]
    i = ac[:, 1].argmax()
    h = harmonics(tr[:, 0], tr[:, 1])
    even, odd = np.sqrt((h[1::2] ** 2).sum()), np.sqrt((h[2::2] ** 2).sum())
    return {"ac_peak_db": ac[i, 1], "ac_peak_hz": ac[i, 0],
            "gain_1k_db": np.interp(F0, ac[:, 0], ac[:, 1]),
            "out_pk_v": np.abs(tr[:, 1] - tr[:, 1].mean()).max(),
            "thd_pct": 100 * np.sqrt((h[1:] ** 2).sum()) / h[0],
            "even_odd": even / odd if odd > 0 else float("inf")}

def run_block(block_id):
    _, meta = load_block(block_id)
    checks = meta.get("dc_checks", {})
    nodes = [c["node"] for c in checks.values()]
    choice = next((k for k, p in meta["params"].items() if p["type"] == "choice"), None)
    variants = meta["params"][choice]["choices"] if choice else [None]
    ok_all = True
    print(f"\n=== {block_id} ===")
    for var in variants:
        ov = {choice: var} if choice else {}
        for amp in AMPS:
            r, res = simulate(block_id, ov, amp, nodes)
            if not all(k in res for k in ("op", "ac", "tran")):
                print(f"  {var}: SIMULATION FAILED\n{r.stdout[-800:]}")
                ok_all = False; continue
            opv = np.atleast_2d(res["op"])[0, 1::2]
            dc = {n: v for n, v in zip(nodes, opv)}
            bad = [f"{n}={dc[c['node']]:.2f}" for n, c in checks.items()
                   if not c["expect"][0] <= dc[c["node"]] <= c["expect"][1]]
            ok_all &= not bad
            m = metrics(res)
            dcs = " ".join(f"{n}={v:.2f}" for n, v in dc.items())
            print(f"  {choice}={var!s:8s} in={amp*1e3:3.0f}mV | DC {dcs} {'OK' if not bad else 'FAIL ' + str(bad)}"
                  f" | 1k {m['gain_1k_db']:5.1f} dB, peak {m['ac_peak_db']:5.1f} dB @ {m['ac_peak_hz']:5.0f} Hz"
                  f" | out {m['out_pk_v']:.2f} V, THD {m['thd_pct']:5.1f}%, even/odd {m['even_odd']:.2f}")
    return ok_all

if __name__ == "__main__":
    ids = sys.argv[1:] or sorted(p.name for p in (LIB / "blocks").iterdir() if p.is_dir())
    results = {b: run_block(b) for b in ids}
    print("\nSummary:", {b: "PASS" if ok else "FAIL" for b, ok in results.items()})
    sys.exit(0 if all(results.values()) else 1)
