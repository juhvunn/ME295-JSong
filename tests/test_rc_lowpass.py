"""Checker validation: RC low-pass -3 dB point at 1/(2*pi*R*C)."""
import math
import shutil
from pathlib import Path

import numpy as np
import pytest

from src.config import load_config
from src.tools.build import build_netlist
from src.tools.evaluate import f_minus3db
from src.tools.simulate import UnsafeNetlistError, check_netlist, read_wrdata, simulate

R, C = 10e3, 10e-9
FC = 1 / (2 * math.pi * R * C)  # ~1591.5 Hz
# Gain is -3.0103 dB exactly at FC, so the -3.000 dB point sits ~0.25% below it.
REL_TOL = 0.01


def ngspice_available() -> bool:
    exe = load_config()["ngspice"]["executable"]
    return shutil.which(exe) is not None or Path(exe).is_file()


def test_f_minus3db_on_analytic_response():
    freq = np.logspace(1, 5, 401)
    gain_db = -10 * np.log10(1 + (freq / FC) ** 2)
    assert f_minus3db(freq, gain_db) == pytest.approx(FC, rel=REL_TOL)


@pytest.mark.skipif(not ngspice_available(), reason="ngspice executable from config.yaml not found")
def test_rc_lowpass_minus3db_matches_formula():
    netlist = build_netlist("rc_lowpass.cir", {
        "R": R, "C": C, "AC_PPD": 100, "AC_FSTART": 10, "AC_FSTOP": 100e3,
    })
    res = simulate(netlist)
    assert res.ok, f"ngspice failed (returncode={res.returncode}, timed_out={res.timed_out}); see {res.log_path}"

    freq, gain_db = read_wrdata(res.run_dir / "ac.txt", n_vectors=1)
    assert f_minus3db(freq, gain_db[:, 0]) == pytest.approx(FC, rel=REL_TOL)


@pytest.mark.parametrize("bad", [
    ".include evil.lib",
    ".SHELL rm -rf /",
    ".control\nshell dir\n.endc",
    ".control\nsource other.cir\n.endc",
    ".control\nwrdata ../../outside.txt v(out)\n.endc",
])
def test_check_netlist_rejects_dangerous_directives(bad):
    with pytest.raises(UnsafeNetlistError):
        check_netlist("* test\nR1 a 0 1k\n" + bad + "\n.end\n")


def test_check_netlist_accepts_templates():
    check_netlist(build_netlist("rc_lowpass.cir", {
        "R": R, "C": C, "AC_PPD": 100, "AC_FSTART": 10, "AC_FSTOP": 100e3,
    }))
