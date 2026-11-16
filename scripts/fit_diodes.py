"""Fit SPICE diode parameters (Is, N, Rs) to datasheet I-V points.

Model: V = N*Vt*ln(I/Is + 1) + I*Rs at the datasheet temperature (TNOM in the
.model line, so ngspice simulates the same curve at that temperature).
Least squares on the voltage error; points come from models/diode_points.yaml.
Writes models/diodes_fitted.lib and prints the error at every datasheet point
and the model voltage below the lowest point (extrapolated region).

Usage: python -m scripts.fit_diodes
"""
import math
import sys

import numpy as np
import yaml
from scipy.optimize import least_squares

from pedal_agent.config import REPO_ROOT

POINTS = REPO_ROOT / "models" / "diode_points.yaml"
OUT = REPO_ROOT / "models" / "diodes_fitted.lib"
K_OVER_Q = 8.617333262e-5  # V/K


def vt(temp_c: float) -> float:
    return K_OVER_Q * (temp_c + 273.15)


def model_v(i, is_, n, rs, temp_c):
    return n * vt(temp_c) * np.log(np.asarray(i) / is_ + 1.0) + np.asarray(i) * rs


def fit(i, v, temp_c):
    """Return (Is, N, Rs). Parameters: log10(Is), N, Rs; bounds keep them physical."""
    def resid(p):
        return model_v(i, 10 ** p[0], p[1], p[2], temp_c) - v
    best = None
    for n0 in (1.0, 1.5, 2.0, 3.0):          # a few starting points; keep the best
        is0 = i[0] / math.exp(v[0] / (n0 * vt(temp_c)))
        r = least_squares(resid, [math.log10(is0), n0, 1.0], bounds=([-40, 0.5, 0.0], [-3, 6.0, 1e3]))
        if best is None or r.cost < best.cost:
            best = r
    return 10 ** best.x[0], best.x[1], best.x[2]


def main() -> int:
    data = yaml.safe_load(POINTS.read_text(encoding="utf-8"))
    temp_c = data["temperature_c"]
    lines = ["* Diode models fitted to datasheet I-V points by scripts/fit_diodes.py.",
             "* GENERATED FILE: edit models/diode_points.yaml and rerun the script.",
             "* Sources, points and fit errors: models/diode_points.yaml and models/README.md."]
    for name, d in data["diodes"].items():
        pts = d["fit_points"]
        i = np.array([p["I"] for p in pts], float)
        v = np.array([p["V"] for p in pts], float)
        is_, n, rs = fit(i, v, temp_c)
        err = (model_v(i, is_, n, rs, temp_c) - v) * 1e3
        print(f"\n{name}: Is={is_:.4g} A  N={n:.4f}  Rs={rs:.4g} Ohm   (fit range {d['fit_range']})")
        print(f"  {'I':>10s} {'V datasheet':>12s} {'V model':>9s} {'error':>9s}   source")
        for p, e in zip(pts, err):
            print(f"  {p['I']:10.3g} {p['V']:12.4f} {p['V'] + e / 1e3:9.4f} {e:+8.1f}mV   {p['ref']}")
        print(f"  max |error| {np.max(np.abs(err)):.1f} mV, rms {np.sqrt(np.mean(err ** 2)):.1f} mV")
        for p in d.get("check_points") or []:
            vm = float(model_v(p["I"], is_, n, rs, temp_c))
            print(f"  check (not fitted) I={p['I']:.3g}: datasheet {p['V']:.3f} V, model {vm:.3f} V, "
                  f"error {1e3 * (vm - p['V']):+.0f} mV   {p['ref']}")
        lo = i.min()
        extra = [lo / 10, lo / 100, lo / 1000]
        print("  extrapolated below the lowest datasheet point "
              + ", ".join(f"I={x:.3g}: {float(model_v(x, is_, n, rs, temp_c)):.3f} V" for x in extra))
        params = f"Is={is_:.6g} N={n:.6g} Rs={rs:.6g}"
        cap = d.get("capacitance")
        if cap:
            params += f" Cjo={cap['Cjo']:.6g} M={cap['M']:.6g}"
        lines += ["", f"* {d['part']}", f"* {d['document']}", f"* fit range {d['fit_range']}; "
                  f"max |error| {np.max(np.abs(err)):.1f} mV; below {lo:.3g} A is extrapolated",
                  f".model {name} D({params} Tnom={temp_c:g})"]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
