"""Part-model validation against datasheet values (see models/README.md for sources)."""
import numpy as np
import pytest

from pedal_agent.config import REPO_ROOT
from pedal_agent.tools.evaluate import f_minus3db
from pedal_agent.tools.simulate import check_netlist, read_wrdata, simulate
from tests.test_rc_lowpass import ngspice_available

pytestmark = pytest.mark.skipif(not ngspice_available(), reason="ngspice executable from config.yaml not found")

OPAMPS_LIB = REPO_ROOT / "models" / "opamps.lib"

# name: (GBW Hz, SR V/s, AOL V/V, swing points [(supply_pm, RL, expected |Vout|)])
OPAMPS = {
    "JRC4558_HALF": (3e6, 1e6, 1e5, [(15, 2e3, 13.0), (6, 2e3, 4.0)]),   # NJM4558 Ver.20260723 p.2, p.4
    "LM741": (1.17e6, 0.5e6, 2e5, [(15, 2e3, 13.0)]),                   # TI SNOSC25D p.5 (GBW p.5/p.6)
}


def run(body: str, control: str) -> "SimResult":
    net = f"* model test\n{OPAMPS_LIB.read_text(encoding='utf-8')}\n{body}\n.control\n{control}\n.endc\n.end\n"
    res = simulate(net)
    assert res.ok, f"ngspice failed; see {res.log_path}"
    return res


def supplies(pm: float) -> str:
    return f"Vp vcc 0 {pm}\nVn vee 0 {-pm}"


def test_model_file_passes_sandbox_filter():
    check_netlist(OPAMPS_LIB.read_text(encoding="utf-8"))
    text = OPAMPS_LIB.read_text(encoding="utf-8").lower()
    assert ".include" not in text and "\n.lib" not in text


@pytest.mark.parametrize("name", OPAMPS)
def test_gain_bandwidth(name):
    gbw = OPAMPS[name][0]
    res = run(f"{supplies(15)}\nVin in 0 DC 0 AC 1\nX1 in fb vcc vee out {name}\nRf out fb 100k\nRg fb 0 1k",
              "ac dec 100 10 10Meg\nwrdata ac.txt vdb(out)")
    f, g = read_wrdata(res.run_dir / "ac.txt", 1)
    measured = f_minus3db(f, g[:, 0]) * 101
    print(f"{name}: GBW {measured / 1e6:.3f} MHz (datasheet {gbw / 1e6:.3g})")
    assert measured == pytest.approx(gbw, rel=0.10)


@pytest.mark.parametrize("name", OPAMPS)
def test_slew_rate(name):
    sr = OPAMPS[name][1]
    res = run(f"{supplies(15)}\nVin in 0 PULSE(-5 5 5u 1n 1n 100u 200u)\nX1 in out vcc vee out {name}\nRL out 0 10k",
              "tran 20n 60u\nwrdata tran.txt v(out)")
    t, v = read_wrdata(res.run_dir / "tran.txt", 1)
    v = v[:, 0]
    lo, hi = -5 + 0.1 * 10, -5 + 0.9 * 10
    t10 = np.interp(lo, v[t > 5e-6], t[t > 5e-6])
    t90 = np.interp(hi, v[t > 5e-6], t[t > 5e-6])
    measured = (hi - lo) / (t90 - t10)
    print(f"{name}: SR {measured / 1e6:.3f} V/us (datasheet {sr / 1e6:.3g})")
    assert measured == pytest.approx(sr, rel=0.10)


@pytest.mark.parametrize("name", OPAMPS)
def test_open_loop_gain(name):
    aol = OPAMPS[name][2]
    res = run(f"{supplies(15)}\nVin in 0 DC 0 AC 1\nX1 in out vcc vee out {name}\nRL out 0 2k",
              "set wr_singlescale\nset wr_vecnames\nac dec 10 0.01 1\nwrdata ac.txt vdb(out) vdb(in,out)")
    f, g = read_wrdata(res.run_dir / "ac.txt", 2)
    measured_db = g[0, 0] - g[0, 1]          # |Vout / (Vinp - Vinn)| at 0.01 Hz
    print(f"{name}: AOL {measured_db:.1f} dB (datasheet {20 * np.log10(aol):.1f} dB)")
    assert measured_db == pytest.approx(20 * np.log10(aol), abs=1.0)


@pytest.mark.parametrize("name, pm, rl, expected",
                         [(n, pm, rl, e) for n, spec in OPAMPS.items() for pm, rl, e in spec[3]])
def test_output_swing(name, pm, rl, expected):
    out = []
    for sign in (1, -1):
        res = run(f"{supplies(pm)}\nVin in 0 {sign}\nX1 in 0 vcc vee out {name}\nRL out 0 {rl}",
                  "op\nwrdata op.txt v(out)")
        out.append(float(np.atleast_2d(np.loadtxt(res.run_dir / "op.txt"))[0, 1]))
    print(f"{name}: +-{pm} V, RL={rl:g}: {out[0]:.2f} / {out[1]:.2f} V (datasheet +-{expected})")
    assert out[0] == pytest.approx(expected, abs=0.15)
    assert out[1] == pytest.approx(-expected, abs=0.15)


@pytest.mark.parametrize("name", OPAMPS)
def test_single_9v_supply_swing_is_reported(name):
    """Extrapolation to the pedal supply (9 V single, RL 2k to Vcc/2): reported, loosely checked."""
    swing = []
    for vin in (9.0, 0.0):
        res = run(f"Vp vcc 0 9\nVb bias 0 4.5\nVin in 0 {vin}\nX1 in bias vcc 0 out {name}\nRL out bias 2k",
                  "op\nwrdata op.txt v(out)")
        swing.append(float(np.atleast_2d(np.loadtxt(res.run_dir / "op.txt"))[0, 1]))
    print(f"{name}: 9 V single supply, RL=2k to 4.5 V: output {swing[1]:.2f} .. {swing[0]:.2f} V")
    assert 1.5 < swing[1] < 2.5 and 6.5 < swing[0] < 7.5


# ---------- diodes (A2): fitted models reproduce their datasheet points ----------
import yaml  # noqa: E402

DIODE_LIB = REPO_ROOT / "models" / "diodes_fitted.lib"
DIODE_DATA = yaml.safe_load((REPO_ROOT / "models" / "diode_points.yaml").read_text(encoding="utf-8"))
# tolerance per model (V): plan C: +-20 mV for silicon; +-3 % of VF for the LED
DIODE_TOL = {"D1N914": lambda v: 0.020, "DLED_RED": lambda v: 0.03 * v}


def test_diode_file_passes_sandbox_filter():
    check_netlist(DIODE_LIB.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", list(DIODE_DATA["diodes"]))
def test_fitted_diode_reproduces_datasheet_points(name):
    pts = DIODE_DATA["diodes"][name]["fit_points"]
    body = "\n".join(f"I{k} 0 a{k} DC {p['I']:g}\nD{k} a{k} 0 {name}" for k, p in enumerate(pts))
    net = (f"* diode test\n{DIODE_LIB.read_text(encoding='utf-8')}\n.temp {DIODE_DATA['temperature_c']}\n{body}\n"
           f".control\nop\nwrdata op.txt {' '.join(f'v(a{k})' for k in range(len(pts)))}\nquit\n.endc\n.end\n")
    res = simulate(net)
    assert res.ok, f"ngspice failed; see {res.log_path}"
    v_sim = np.atleast_2d(np.loadtxt(res.run_dir / "op.txt"))[0, 1::2]
    tol = DIODE_TOL[name]
    for p, v in zip(pts, v_sim):
        print(f"{name}: I={p['I']:.3g} A  datasheet {p['V']:.4f} V  ngspice {v:.4f} V  error {1e3 * (v - p['V']):+.1f} mV")
        assert v == pytest.approx(p["V"], abs=tol(p["V"])), p["ref"]


# ---------- transistors (B2): fitted Gummel-Poon models vs datasheet ----------
from scripts.fit_bjts import hfe_targets, load as load_bjt_data, vbe_for as model_vbe, fit_all  # noqa: E402

BJT_LIB = REPO_ROOT / "models" / "bjts_fitted.lib"
BJT_DATA = load_bjt_data()
BJT_PARAMS = fit_all(BJT_DATA)


def bjt_op(name, points):
    """points: [(Ic_target, VCE)] -> list of (Ic, Ib, VBE) from ngspice at 25 C."""
    p = BJT_PARAMS[name]
    body, vecs = [], []
    for k, (ic, vce) in enumerate(points):
        vbe = model_vbe(ic, vce, p)
        body.append(f"Vc{k} c{k} 0 DC {vce:g}\nVb{k} b{k} 0 DC {vbe:.9g}\nQ{k} c{k} b{k} 0 {name}")
        vecs += [f"i(vc{k})", f"i(vb{k})"]
    net = (f"* bjt test\n{BJT_LIB.read_text(encoding='utf-8')}\n.temp 25\n" + "\n".join(body) +
           f"\n.control\nop\nwrdata op.txt {' '.join(vecs)}\nquit\n.endc\n.end\n")
    res = simulate(net)
    assert res.ok, f"ngspice failed; see {res.log_path}"
    v = np.atleast_2d(np.loadtxt(res.run_dir / "op.txt"))[0, 1::2]
    return [(-v[2 * k], -v[2 * k + 1], model_vbe(ic, vce, p)) for k, (ic, vce) in enumerate(points)]


def test_bjt_file_passes_sandbox_filter():
    check_netlist(BJT_LIB.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", list(BJT_DATA["transistors"]))
def test_bjt_hfe_matches_nominal_curve(name):
    t = BJT_DATA["transistors"][name]
    target, _ = hfe_targets(t)
    vce = t["hfe_shape"]["vce"]
    for (ic_t, h_t), (ic, ib, _) in zip(target, bjt_op(name, [(i, vce) for i, _ in target])):
        print(f"{name}: Ic {ic * 1e3:.3g} mA  hFE ngspice {ic / ib:.1f}  target {h_t:.1f}")
        assert ic == pytest.approx(ic_t, rel=0.01)
        assert ic / ib == pytest.approx(h_t, rel=0.10)


@pytest.mark.parametrize("name", list(BJT_DATA["transistors"]))
def test_bjt_vbe_matches_datasheet(name):
    vb = BJT_DATA["transistors"][name]["vbe"]
    pts = [vb["anchor"]] if vb["mode"] == "anchor" else vb["points"]
    for (i, v), (ic, _, vbe) in zip(pts, bjt_op(name, [(i, vb["vce"]) for i, _ in pts])):
        print(f"{name}: Ic {ic * 1e3:.3g} mA  VBE model {vbe:.4f}  datasheet {v:.4f}")
        assert ic == pytest.approx(i, rel=0.01)
        assert vbe == pytest.approx(v, abs=0.010)


@pytest.mark.parametrize("name", list(BJT_DATA["transistors"]))
def test_bjt_hfe_within_datasheet_limits(name):
    t = BJT_DATA["transistors"][name]
    spec, vce = t["hfe_spec"], t["hfe_shape"]["vce"]
    (ic, ib, _), = bjt_op(name, [(spec["I"], spec["vce"])])
    assert spec["min"] <= ic / ib <= spec["max"]
    for (i, mn), (ic, ib, _) in zip(t["hfe_table_min"], bjt_op(name, [(i, vce) for i, _ in t["hfe_table_min"]])):
        assert ic / ib >= mn, f"{name}: hFE {ic / ib:.1f} below table minimum {mn} at {i * 1e3:g} mA"


@pytest.mark.parametrize("name", list(BJT_DATA["transistors"]))
def test_bjt_ft_near_datasheet(name):
    f = BJT_DATA["transistors"][name]["ft"]
    vbe = model_vbe(f["ic"], f["vce"], BJT_PARAMS[name])
    net = (f"* ft test\n{BJT_LIB.read_text(encoding='utf-8')}\n.temp 25\nVc c 0 DC {f['vce']:g}\n"
           f"Vb b 0 DC {vbe:.9g} AC 1\nQ1 c b 0 {name}\n.control\nset wr_singlescale\nset wr_vecnames\n"
           f"ac dec 50 1Meg 10G\n"
           f"wrdata ac.txt mag(i(vc)) mag(i(vb))\nquit\n.endc\n.end\n")
    res = simulate(net)
    assert res.ok, f"ngspice failed; see {res.log_path}"
    freq, m = read_wrdata(res.run_dir / "ac.txt", 2)
    beta = m[:, 0] / m[:, 1]
    ft = 10 ** np.interp(0.0, -np.log10(beta), np.log10(freq))   # |ic/ib| = 1
    print(f"{name}: fT {ft / 1e6:.0f} MHz (datasheet {f['value'] / 1e6:.0f} MHz, {f['kind']})")
    assert ft == pytest.approx(f["value"], rel=0.25)
