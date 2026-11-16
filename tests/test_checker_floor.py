"""Checker THD noise floor (CLAUDE.md: "pure sine THD ~ 0"). Linear signals go through the same
analyses and THD code as check(); the measured floor sets the benchmark THD rules (docs/phase3_plan.md)."""
import numpy as np
import pytest

from pedal_agent.checker import ANALYSES, THD_FLOOR_PCT, distortion, models_text
from pedal_agent.harness import netlist
from pedal_agent.tools.simulate import simulate as run_ngspice

F0, AMP = 1000.0, 0.3
PASSIVE = (".subckt LIN_R in out vcc gnd\nR1 in out 10k\nR2 out gnd 10k\n.ends", "LIN_R")
# non-inverting op-amp, gain 1 + Rf/Rg = 2, biased at VCC/2, far from the rails at 300 mV
OPAMP = (""".subckt LIN_OA in out vcc gnd
Cin in a 1u
Rb1 vcc b 100k
Rb2 b gnd 100k
Cb b gnd 10u
Rin a b 1Meg
XU a fb vcc gnd o JRC4558_HALF
Rf o fb 10k
Rg fb c 10k
Cg c b 10u
Cout o out 1u
Rout out gnd 100k
.ends""", "LIN_OA")


def tran(block):
    r = run_ngspice(netlist([block], models_text(), AMP, F0, "\n".join(ANALYSES)))
    return np.loadtxt(r.run_dir / "tran.txt")       # columns: t, v(emf), t, v(out)


def test_ideal_sine_is_at_the_floor():
    t = np.arange(40e-3, 60e-3 + 1e-12, 5e-6)          # same window and step as the transient
    thd, _ = distortion(t, AMP * np.sin(2 * np.pi * F0 * t), F0)
    assert thd <= THD_FLOOR_PCT


@pytest.mark.slow
@pytest.mark.parametrize("block", [PASSIVE, OPAMP], ids=["passive", "opamp_x2"])
def test_linear_chain_is_at_the_floor(block):
    tr = tran(block)
    thd_src, _ = distortion(tr[:, 0], tr[:, 1], F0)     # source sine as ngspice sampled it
    thd_out, _ = distortion(tr[:, 0], tr[:, 3], F0)
    assert thd_src <= THD_FLOOR_PCT and thd_out <= THD_FLOOR_PCT
    if block is OPAMP:
        assert 0.5 < np.ptp(tr[:, 3]) / 2 < 0.7          # gain ~2 (pickup adds a little at 1 kHz)
