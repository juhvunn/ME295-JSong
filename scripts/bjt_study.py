"""Transistor operating currents and model sensitivity (models step B2).

1. Operating currents of fuzz_ff_si Q1/Q2 and the od_ts808 buffers with the fitted models
   (default settings; no signal and 300 mV / 1 kHz).
2. Sensitivity: variants of each fitted transistor
     hfe_min / hfe_max : hFE scaled to the datasheet min / max at the spec current (BF*k, ISE/k)
     nf_1.00           : VBE slope NF = 1.0 (physical lower bound), pivoting at the lowest VBE data point
     nf_high           : 2N3904 only, NF = 1.20 (highest h-parameter estimate)
   fuzz_ff_si (both Q_model choices): DC bias V(b1), V(c1), V(c2), DC checks, gain_1k_db, thd_pct,
   even_odd, out_pk_v. od_ts808 (2N4401): DC checks and buffer emitter voltages, plus metrics.
3. 2N3904 cross-check: small-signal hfe (VCE = 10 V) of the nominal and hfe_min models vs Fig. 11.

Model set: models/opamps.lib + diodes_fitted.lib + bjts_fitted.lib (variant substituted) + what is
left of smoke_models.lib (only the unvalidated DGE).

Usage: python -m scripts.bjt_study
"""
import re
import sys
import tempfile
from pathlib import Path

import numpy as np

import pedal_agent.checker as checker
from pedal_agent.build import load_block, render
from pedal_agent.config import REPO_ROOT
from pedal_agent.harness import netlist
from pedal_agent.schemas import BlockInstance, Candidate, TargetSpec
from pedal_agent.tools.simulate import simulate
from scripts.fit_bjts import fit_all, load, model_line, scale_hfe, small_signal_hfe, with_nf

MODELS = REPO_ROOT / "models"
REPLACED_SUBCKTS = ("JRC4558_HALF", "LM741")
REPLACED_MODELS = ("D1N914", "DLED_RED", "Q2N3904", "Q2N4401", "QBC549C")


def remaining_placeholders() -> str:
    text = (MODELS / "smoke_models.lib").read_text(encoding="utf-8")
    for name in REPLACED_SUBCKTS:
        text = re.sub(rf"(?ims)^\.subckt {name}\b.*?^\.ends\b[^\n]*\n", "", text)
    for name in REPLACED_MODELS:
        text = re.sub(rf"(?im)^\.model {name}\b[^\n]*\n", "", text)
    return text


def model_set(bjt_override: dict[str, str] | None = None) -> str:
    bjts = (MODELS / "bjts_fitted.lib").read_text(encoding="utf-8")
    for name, line in (bjt_override or {}).items():
        bjts = re.sub(rf"(?im)^\.model {name} NPN\b[^\n]*$", line, bjts)
    return "\n".join([(MODELS / "opamps.lib").read_text(encoding="utf-8"),
                      (MODELS / "diodes_fitted.lib").read_text(encoding="utf-8"), bjts, remaining_placeholders()])


def variants(name, p, t):
    spec = t["hfe_spec"]
    nominal = (spec["min"] * spec["max"]) ** 0.5
    vb = t["vbe"]
    pivot = vb["anchor"] if vb["mode"] == "anchor" else vb["points"][0]
    out = {"nominal": p, "hfe_min": scale_hfe(p, spec["min"] / nominal),
           "hfe_max": scale_hfe(p, spec["max"] / nominal),
           "nf_1.00": with_nf(p, 1.0, pivot[0], pivot[1], vb["vce"])}
    if name == "Q2N3904":
        out["nf_1.20"] = with_nf(p, 1.20, pivot[0], pivot[1], vb["vce"])
    return out


def op_values(block, params, lib, nodes):
    _, meta = load_block(block)
    ctrl = f"op\nwrdata op.txt {' '.join(f'v(x1.{n})' for n in nodes)}"
    res = simulate(netlist([(render(block, params), meta["subckt"])], lib, 0.3, 1000.0, ctrl))
    assert res.ok, res.log_path
    return dict(zip(nodes, np.atleast_2d(np.loadtxt(res.run_dir / "op.txt"))[0, 1::2]))


def metrics(block, params, lib):
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "models.lib"
        path.write_text(lib, encoding="utf-8")
        old, checker.MODELS = checker.MODELS, str(path)
        try:
            return checker.check(Candidate(chain=[BlockInstance(block_id=block, params=params)], rationale=""),
                                 TargetSpec(goal_text="", targets=[]))
        finally:
            checker.MODELS = old


def currents(lib):
    rows = []
    for block, nodes in (("fuzz_ff_si", ("c1", "c2", "na")), ("od_ts808", ("e1", "e2", "n6"))):
        _, meta = load_block(block)
        p = render(block, {})
        for amp in (0.0, 0.3):
            ctrl = f"tran 5u 60m 40m\nwrdata tran.txt {' '.join(f'v(x1.{n})' for n in nodes)}"
            res = simulate(netlist([(p, meta["subckt"])], lib, amp, 1000.0, ctrl))
            assert res.ok, res.log_path
            d = np.loadtxt(res.run_dir / "tran.txt")
            w = np.gradient(d[:, 0])
            if block == "fuzz_ff_si":
                r5 = float(next(l for l in p.splitlines() if l.startswith("R5 ")).split()[3])
                pairs = (("Q1", (9.0 - d[:, 1]) / 33e3), ("Q2", (d[:, 5] - d[:, 3]) / r5))
            else:
                pairs = (("Q1 buffer", d[:, 1] / 10e3), ("Q2 buffer", d[:, 3] / 10e3 + (d[:, 3] - d[:, 5]) / 100.0))
            for name, i in pairs:
                frac = lambda lo, hi: float(np.sum(w[(i >= lo) & (i < hi)]) / np.sum(w))  # noqa: E731
                rows.append((block, "no signal" if amp == 0 else "300 mV", name, i.min(), i.max(),
                             frac(-1, 10e-6), frac(10e-6, 1e-3), frac(1e-3, 1)))
    return rows


def main() -> int:
    data = load()
    params = fit_all(data)
    lib = model_set()

    print("1. Operating currents with the fitted models (default settings)")
    for block, sig, name, lo, hi, f0, f1, f2 in currents(lib):
        print(f"  {block:11s} {sig:9s} {name:10s} Ic {lo * 1e6:8.1f} .. {hi * 1e6:8.1f} uA | "
              f"<10uA {f0:4.0%}  10uA-1mA {f1:4.0%}  >1mA {f2:4.0%}")

    print("\n2. Sensitivity")
    for name in ("Q2N3904", "QBC549C"):
        print(f"  fuzz_ff_si, Q_model={name}")
        for label, p in variants(name, params[name], data["transistors"][name]).items():
            vlib = model_set({name: model_line(name, p)})
            bias = op_values("fuzz_ff_si", {"Q_model": name}, vlib, ("b1", "c1", "c2"))
            rep = metrics("fuzz_ff_si", {"Q_model": name}, vlib)
            m = rep.metrics
            print(f"    {label:8s} V(b1) {bias['b1']:.3f}  V(c1) {bias['c1']:.3f}  V(c2) {bias['c2']:.3f}  "
                  f"DC {'ok' if rep.dc_ok else rep.errors}  gain {m['gain_1k_db']:6.2f} dB  THD {m['thd_pct']:5.1f}%  "
                  f"even/odd {m['even_odd']:.3f}  out_pk {m['out_pk_v'] * 1e3:6.1f} mV")
    print("  od_ts808, 2N4401 buffers")
    for label, p in variants("Q2N4401", params["Q2N4401"], data["transistors"]["Q2N4401"]).items():
        vlib = model_set({"Q2N4401": model_line("Q2N4401", p)})
        bias = op_values("od_ts808", {}, vlib, ("vr", "o1", "o2", "e1", "e2"))
        rep = metrics("od_ts808", {}, vlib)
        m = rep.metrics
        print(f"    {label:8s} " + "  ".join(f"V({k}) {v:.3f}" for k, v in bias.items()) +
              f"  DC {'ok' if rep.dc_ok else rep.errors}  gain {m['gain_1k_db']:.2f} dB  THD {m['thd_pct']:.2f}%  "
              f"out_pk {m['out_pk_v'] * 1e3:.1f} mV")

    print("\n3. 2N3904 cross-check: small-signal hfe at VCE = 10 V vs Fig. 11")
    t = data["transistors"]["Q2N3904"]
    vs = variants("Q2N3904", params["Q2N3904"], t)
    for i, h in t["hfe_crosscheck"]["points"]:
        print(f"    {i * 1e3:5.2g} mA  Fig.11 {h:6.1f}  nominal {small_signal_hfe(i, 10.0, vs['nominal']):6.1f}  "
              f"hfe_min {small_signal_hfe(i, 10.0, vs['hfe_min']):6.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
