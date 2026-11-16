"""Fit Gummel-Poon NPN models to datasheet curves (models step B2).

Data: models/bjt_points.yaml. Output: models/bjts_fitted.lib (generated, committed).
Forward-active DC equations as in SPICE (cbc and reverse terms included, VAR/IKR/ISC unused):
  cbe = IS(exp(VBE/(NF Vt)) - 1), q1 = 1/(1 - VBC/VAF), q2 = cbe/IKF, qb = q1 (1 + sqrt(1 + 4 q2)) / 2
  IC = (cbe - cbc)/qb - cbc/BR,   IB = cbe/BF + ISE(exp(VBE/(NE Vt)) - 1) + cbc/BR
Steps per part: VBE -> IS (and NF), hFE (nominal = geometric mean of the datasheet min/max at
the spec current x typical normalized shape) -> BF, ISE, NE, IKF, refit IS, then TF from fT.
Capacitances are constant typical values (MJE = MJC = 0). Everything else: SPICE defaults.

Usage: python -m scripts.fit_bjts
"""
import math
import sys

import numpy as np
import yaml
from scipy.optimize import brentq, least_squares

from pedal_agent.config import REPO_ROOT

POINTS = REPO_ROOT / "models" / "bjt_points.yaml"
OUT = REPO_ROOT / "models" / "bjts_fitted.lib"
VT = 8.617333262e-5 * (25 + 273.15)


def currents(v, vce, p):
    cbe = p["IS"] * math.expm1(v / (p["NF"] * VT))
    cbc = p["IS"] * math.expm1((v - vce) / VT)
    q1 = 1.0 / (1.0 - (v - vce) / p["VAF"])
    q2 = cbe / p["IKF"] if p.get("IKF") else 0.0
    qb = q1 * (1 + math.sqrt(1 + 4 * q2)) / 2
    ic = (cbe - cbc) / qb - cbc
    ib = cbe / p["BF"] + p.get("ISE", 0.0) * math.expm1(v / (p.get("NE", 1.5) * VT)) + cbc
    return ic, ib


def vbe_for(ic, vce, p):
    return brentq(lambda v: math.log(currents(v, vce, p)[0] / ic), 0.05, 1.3, xtol=1e-9)


def hfe(ic, vce, p):
    return ic / currents(vbe_for(ic, vce, p), vce, p)[1]


def small_signal_hfe(ic, vce, p, d=1e-4):
    v = vbe_for(ic, vce, p)
    ic1, ib1 = currents(v - d, vce, p)
    ic2, ib2 = currents(v + d, vce, p)
    return (ic2 - ic1) / (ib2 - ib1)


def solve_is(p, ic, vbe, vce):
    """IS such that IC(vbe) = ic. Solved in log10(IS): IS ~ 1e-13 is below brentq's absolute tolerance."""
    f = lambda e: math.log(currents(vbe, vce, {**p, "IS": 10 ** e})[0] / ic)  # noqa: E731
    return 10 ** brentq(f, -24, -6, xtol=1e-12)


def fit_vbe(d, p):
    pts = np.array(d["points"], float)
    lo, hi = d.get("fit_range", [0, 1])
    pts = pts[(pts[:, 0] >= lo * 0.99) & (pts[:, 0] <= hi * 1.01)]
    if d["mode"] == "anchor":
        i0, v0 = d["anchor"]
        return {**p, "IS": solve_is(p, i0, v0, d["vce"])}
    def res(x):
        q = {**p, "IS": 10 ** x[0], "NF": x[1]}
        return [(vbe_for(i, d["vce"], q) - v) * 1e3 for i, v in pts]
    r = least_squares(res, [math.log10(p["IS"]), p["NF"]], bounds=([-20, 0.9], [-10, 2.0]))
    return {**p, "IS": 10 ** r.x[0], "NF": r.x[1]}


def hfe_targets(t):
    shape = t["hfe_shape"]
    pts = np.array(shape["points"], float)
    spec = t["hfe_spec"]
    nominal = math.sqrt(spec["min"] * spec["max"])
    ref = shape.get("normalize_at", spec["I"])
    norm_at_ref = 10 ** np.interp(math.log10(ref), np.log10(pts[:, 0]), np.log10(pts[:, 1]))
    target = pts.copy()
    target[:, 1] = pts[:, 1] / norm_at_ref * nominal
    lo, hi = shape["fit_range"]
    return target[(target[:, 0] >= lo * 0.99) & (target[:, 0] <= hi * 1.01)], nominal


def fit_hfe(t, p):
    target, _ = hfe_targets(t)
    vce = t["hfe_shape"]["vce"]
    no_ise = t["hfe_shape"].get("no_low_current_data", False)
    def unpack(x):
        q = {**p, "BF": 10 ** x[0], "IKF": 10 ** x[1]}
        q.update({"ISE": 0.0, "NE": 1.5} if no_ise else {"ISE": 10 ** x[2], "NE": x[3]})
        return q
    def res(x):
        q = unpack(x)
        return [math.log10(hfe(i, vce, q) / h) for i, h in target]
    x0 = [math.log10(target[:, 1].max() * 1.2), -1.0] + ([] if no_ise else [-13.0, 1.8])
    lb = [1, -3] + ([] if no_ise else [-18, 1.1])
    ub = [4, 1] + ([] if no_ise else [-8, 4.0])
    r = least_squares(res, x0, bounds=(lb, ub))
    return unpack(r.x)


def fit_part(t, vaf):
    p = {"IS": 1e-14, "NF": t.get("nf", {}).get("value", 1.0), "BF": 200.0, "VAF": vaf, "IKF": None}
    for _ in range(3):                     # VBE and hFE interact through qb: iterate
        p = fit_vbe(t["vbe"], p)
        p = fit_hfe(t, p)
    c, f = t["caps"], t["ft"]
    gm = f["ic"] / (p["NF"] * VT)
    p["TF"] = max(1 / (2 * math.pi * f["value"]) - (c["cje"] + c["cjc"]) / gm, 0.0)
    p["CJE"], p["CJC"] = c["cje"], c["cjc"]
    return p


def model_line(name, p):
    return (f".model {name} NPN(IS={p['IS']:.6g} NF={p['NF']:.6g} BF={p['BF']:.6g} ISE={p['ISE']:.6g} "
            f"NE={p['NE']:.6g} IKF={p['IKF']:.6g} VAF={p['VAF']:g} CJE={p['CJE']:.6g} MJE=0 "
            f"CJC={p['CJC']:.6g} MJC=0 TF={p['TF']:.6g} TNOM=25)")


def scale_hfe(p, k):
    """Variant with hFE scaled by k (BF*k, ISE/k)."""
    return {**p, "BF": p["BF"] * k, "ISE": p["ISE"] / k}


def with_nf(p, nf, pivot_i, pivot_v, vce):
    """Variant with a different VBE slope NF, pivoting at the lowest VBE data point."""
    q = {**p, "NF": nf}
    q["IS"] = solve_is(q, pivot_i, pivot_v, vce)
    return q


def load():
    return yaml.safe_load(POINTS.read_text(encoding="utf-8"))


def fit_all(data=None):
    data = data or load()
    return {name: fit_part(t, data["vaf_assumed"]) for name, t in data["transistors"].items()}


def main() -> int:
    data = load()
    params = fit_all(data)
    lines = ["* Transistor models fitted to datasheet curves by scripts/fit_bjts.py (models step B2).",
             "* GENERATED FILE: edit models/bjt_points.yaml and rerun the script.",
             "* Sources, assumptions and fit errors: models/bjt_points.yaml and models/README.md."]
    for name, t in data["transistors"].items():
        p = params[name]
        target, nominal = hfe_targets(t)
        vce_h = t["hfe_shape"]["vce"]
        print(f"\n{name}: {t['part']}")
        print("  " + model_line(name, p))
        print(f"  hFE nominal {nominal:.1f} at {t['hfe_spec']['I'] * 1e3:g} mA (geometric mean of "
              f"{t['hfe_spec']['min']}-{t['hfe_spec']['max']}); model {hfe(t['hfe_spec']['I'], t['hfe_spec']['vce'], p):.1f}")
        print(f"  {'I (mA)':>8s} {'hFE target':>10s} {'model':>8s} {'error':>7s}")
        for i, h in target:
            m = hfe(i, vce_h, p)
            print(f"  {i * 1e3:8.3g} {h:10.1f} {m:8.1f} {100 * (m / h - 1):+6.1f}%")
        for i, mn in t["hfe_table_min"]:
            print(f"  table min at {i * 1e3:g} mA: {mn}; model {hfe(i, vce_h, p):.1f}")
        vb = t["vbe"]
        print(f"  VBE (VCE = {vb['vce']} V; mode {vb['mode']}; lowest datasheet point {vb['lowest_current'] * 1e3:g} mA)")
        for i, v in vb["points"] + vb.get("check_points", []):
            m = vbe_for(i, vb["vce"], p)
            tag = "" if [i, v] in vb["points"] else "  (check, not fitted)"
            print(f"  {i * 1e3:8.3g} mA  datasheet {v:.4f}  model {m:.4f}  error {1e3 * (m - v):+6.1f} mV{tag}")
        print("  extrapolated: " + ", ".join(f"{i * 1e6:g} uA: {vbe_for(i, vb['vce'], p):.4f} V" for i in (1e-5, 1e-6)))
        if "hfe_crosscheck" in t:
            print("  cross-check vs small-signal hfe (VCE = 10 V):")
            for i, h in t["hfe_crosscheck"]["points"]:
                m = small_signal_hfe(i, 10.0, p)
                print(f"    {i * 1e3:6.3g} mA  datasheet {h:6.1f}  model {m:6.1f}  model/datasheet {m / h:.2f}")
        lines += ["", f"* {t['part']}", f"* {t['document']}", model_line(name, p)]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
