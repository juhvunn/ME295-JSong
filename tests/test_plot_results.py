"""Headless plotting tests using synthetic ngspice wrdata files."""
import numpy as np

from scripts.plot_results import plot_run


def test_plot_run_creates_all_pngs(tmp_path):
    run_dir = tmp_path / "synthetic-run"
    run_dir.mkdir()

    frequency = np.logspace(1, 5, 401)
    gain_db = -10.0 * np.log10(1.0 + (frequency / 2000.0) ** 2)
    np.savetxt(run_dir / "ac.txt", np.column_stack((frequency, gain_db)),
               header="frequency db(v(out))", comments="")

    time = np.arange(0.0, 0.010001, 1e-5)
    voltage_in = np.sin(2.0 * np.pi * 1000.0 * time)
    voltage_out = 0.6 * np.tanh(3.0 * voltage_in)
    np.savetxt(run_dir / "tran.txt", np.column_stack((time, voltage_in, voltage_out)),
               header="time v(in) v(out)", comments="")

    output_dir = tmp_path / "plots"
    paths = plot_run(run_dir, output_dir=output_dir)

    assert {path.name for path in paths} == {
        "synthetic-run_ac.png",
        "synthetic-run_tran.png",
        "synthetic-run_transfer.png",
        "synthetic-run_spectrum.png",
    }
    assert all(path.is_file() and path.stat().st_size > 0 for path in paths)
