"""Diode currents in the clipping stages, and LED-model sensitivity (models step A2).

1. Currents: simulates od_ts808 and dist_distplus at default settings (1 kHz, 300 mV pickup EMF)
   for D_clip = si and led, reads the voltage across the clipping diodes and converts it to
   current with the fitted diode equation (Shockley + Rs, solved with the Lambert W function).
2. Sensitivity: runs both blocks with D_clip=led using LED variants whose extrapolated voltage
   at 1 uA spans the range found when fitting different parts of the datasheet curve.

Model set: models/opamps.lib + models/diodes_fitted.lib, with the remaining parts (transistors,
DGE) taken from the placeholder models/smoke_models.lib until models step B replaces them.

Usage: python -m scripts.diode_study
"""
import re
import sys
import tempfile
from pathlib import Path

import numpy as np
import yaml
from scipy.special import lambertw

import pedal_agent.checker as checker
from pedal_agent.build import load_block, render
from pedal_agent.config import REPO_ROOT
from pedal_agent.harness import netlist
from pedal_agent.schemas import BlockInstance, Candidate, TargetSpec
from pedal_agent.tools.simulate import simulate
from scripts.fit_diodes import fit, vt

MODELS = REPO_ROOT / "models"
REPLACED_SUBCKTS = ("JRC4558_HALF", "LM741")
REPLACED_MODELS = ("D1N914", "DLED_RED")
# where the clipping diodes sit in each block template: (node a, node b) of the antiparallel pair
CLIP_NODES = {"od_ts808": ("x1.m1", "x1.o1"), "dist_distplus": ("x1.c", "0")}


def remaining_placeholders() -> str:
    """smoke_models.lib without the parts that now have real models."""
    text = (MODELS / "smoke_models.lib").read_text(encoding="utf-8")
    for name in REPLACED_SUBCKTS:
        text = re.sub(rf"(?ims)^\.subckt {name}\b.*?^\.ends\b[^\n]*\n", "", text)
    for name in REPLACED_MODELS:
        text = re.sub(rf"(?im)^\.model {name}\b[^\n]*\n", "", text)
    return text


def model_set(led_line: str | None = None) -> str:
    diodes = (MODELS / "diodes_fitted.lib").read_text(encoding="utf-8")
    if led_line:
        diodes = re.sub(r"(?im)^\.model DLED_RED\b[^\n]*$", led_line, diodes)
    return "\n".join([(MODELS / "opamps.lib").read_text(encoding="utf-8"), diodes, remaining_placeholders()])


def diode_params(lib: str, name: str) -> dict:
    line = re.search(rf"(?im)^\.model {name} D\((.*)\)", lib).group(1)
    return {k.lower(): float(v) for k, v in re.findall(r"(\w+)=([-+0-9.eE]+)", line)}


def current(v, p, temp_c=27.0):
    """Forward current of one diode for voltage v (Shockley + Rs), via Lambert W."""
    n_vt, is_, rs = p["n"] * vt(temp_c), p["is"], p["rs"]
    if rs == 0:
        return is_ * (np.exp(v / n_vt) - 1)
    x = is_ * rs / n_vt * np.exp(np.clip((v + is_ * rs) / n_vt, None, 700))
    return np.real(n_vt / rs * lambertw(x)) - is_


def clip_currents(block: str, choice: str, lib: str) -> dict:
    _, meta = load_block(block)
    a, b = CLIP_NODES[block]
    vb = f"v({b})" if b != "0" else "v(x1.c)*0"
    ctrl = f"tran 5u 60m 40m\nwrdata tran.txt v({a}) {vb}"
    net = netlist([(render(block, {"D_clip": choice}), meta["subckt"])], lib, 0.3, 1000.0, ctrl)
    res = simulate(net)
    assert res.ok, f"ngspice failed; see {res.log_path}"
    d = np.loadtxt(res.run_dir / "tran.txt")
    vd = d[:, 1] - d[:, 3]
    p = diode_params(lib, {"si": "D1N914", "led": "DLED_RED"}[choice])
    i = current(vd, p) - current(-vd, p)          # antiparallel pair
    t = d[:, 0]
    w = np.gradient(t)                             # time weights (adaptive step)
    frac = lambda lo, hi: float(np.sum(w[(np.abs(i) >= lo) & (np.abs(i) < hi)]) / np.sum(w))  # noqa: E731
    return {"vd_peak": float(np.abs(vd).max()), "i_peak": float(np.abs(i).max()),
            "i_rms": float(np.sqrt(np.sum(w * i ** 2) / np.sum(w))),
            "time <1uA": frac(0, 1e-6), "time 1-100uA": frac(1e-6, 100e-6),
            "time 0.1-1mA": frac(100e-6, 1e-3), "time >1mA": frac(1e-3, np.inf)}


def led_variants() -> dict[str, str]:
    data = yaml.safe_load((MODELS / "diode_points.yaml").read_text(encoding="utf-8"))
    led = data["diodes"]["DLED_RED"]
    pts = led["fit_points"] + led["check_points"]
    i = np.array([p["I"] for p in pts]); v = np.array([p["V"] for p in pts])
    out = {}
    for label, mask in [("low  (fit 1-20 mA)", i >= 1e-3), ("mid  (fit 0.1-20 mA)", i > 0),
                        ("high (fit 0.1-10 mA, chosen)", i <= 10.0e-3)]:
        is_, n, rs = fit(i[mask], v[mask], data["temperature_c"])
        v1u = n * vt(data["temperature_c"]) * np.log(1e-6 / is_ + 1) + 1e-6 * rs
        out[f"{label}, V(1uA)={v1u:.3f} V"] = (f".model DLED_RED D(Is={is_:.6g} N={n:.6g} Rs={rs:.6g} "
                                               f"Tnom={data['temperature_c']:g})")
    return out


def main() -> int:
    lib = model_set()
    print("1. Clipping-diode currents at default settings (1 kHz, 300 mV EMF; fraction of time in each band)")
    for block in CLIP_NODES:
        for choice in ("si", "led"):
            r = clip_currents(block, choice, lib)
            print(f"  {block:14s} D_clip={choice:4s} Vd peak {r['vd_peak']:.3f} V, I peak {r['i_peak'] * 1e6:8.1f} uA, "
                  f"I rms {r['i_rms'] * 1e6:7.1f} uA | <1uA {r['time <1uA']:.0%}  1-100uA {r['time 1-100uA']:.0%}  "
                  f"0.1-1mA {r['time 0.1-1mA']:.0%}  >1mA {r['time >1mA']:.0%}")

    print("\n2. LED sensitivity (D_clip=led, defaults)")
    spec = TargetSpec(goal_text="", targets=[])
    keys = ("gain_1k_db", "thd_pct", "out_pk_v", "even_odd")
    with tempfile.TemporaryDirectory() as td:
        for block in CLIP_NODES:
            print(f"  {block}")
            for label, line in led_variants().items():
                path = Path(td) / "models.lib"
                path.write_text(model_set(line), encoding="utf-8")
                checker.MODELS = str(path)
                rep = checker.check(Candidate(chain=[BlockInstance(block_id=block, params={"D_clip": "led"})],
                                              rationale=""), spec)
                assert not rep.errors, rep.errors
                print(f"    {label:48s} " + "  ".join(f"{k} {rep.metrics[k]:.4g}" for k in keys))
    return 0


if __name__ == "__main__":
    sys.exit(main())
