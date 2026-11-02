"""Plot AC and transient outputs from an ngspice run directory."""
from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import REPO_ROOT, load_config  # noqa: E402
from src.tools.evaluate import f_minus3db  # noqa: E402
from src.tools.simulate import read_wrdata  # noqa: E402


def _latest_run_dir() -> Path:
    runs_dir = REPO_ROOT / load_config()["paths"]["runs_dir"]
    run_dirs = [path for path in runs_dir.iterdir() if path.is_dir()]
    if not run_dirs:
        raise FileNotFoundError(f"no run directories found in {runs_dir}")
    return max(run_dirs, key=lambda path: path.name)


def plot_run(
    run_dir: str | Path | None = None,
    *,
    output_dir: str | Path | None = None,
    full: bool = False,
    show: bool = False,
) -> list[Path]:
    """Save AC, transient, transfer, and visual spectrum plots for a run."""
    run_dir = Path(run_dir) if run_dir is not None else _latest_run_dir()
    if not run_dir.is_dir():
        raise FileNotFoundError(f"run directory does not exist: {run_dir}")

    cfg = load_config()
    with (REPO_ROOT / cfg["protocol"]).open(encoding="utf-8") as protocol_file:
        protocol = yaml.safe_load(protocol_file)
    transient_protocol = protocol["transient"]

    frequency, ac_values = read_wrdata(run_dir / "ac.txt", n_vectors=1)
    gain_db = ac_values[:, 0]
    time, transient_values = read_wrdata(run_dir / "tran.txt", n_vectors=2)
    voltage_in, voltage_out = transient_values[:, 0], transient_values[:, 1]

    steady_mask = time >= transient_protocol.get("settle_s", 0.0)
    steady_time = time[steady_mask]
    steady_in = voltage_in[steady_mask]
    steady_out = voltage_out[steady_mask]
    if steady_time.size < 2:
        raise ValueError("transient output has fewer than two steady-state samples")

    cutoff_frequency = f_minus3db(frequency, gain_db)
    cutoff_gain = gain_db[0] - 3.0
    output_dir = Path(output_dir) if output_dir is not None else REPO_ROOT / "results" / "plots"
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = run_dir.name
    outputs = []

    figure, axis = plt.subplots()
    axis.semilogx(frequency, gain_db)
    axis.axhline(cutoff_gain, color="tab:red", linestyle="--", label="-3 dB from low-frequency gain")
    axis.plot(cutoff_frequency, cutoff_gain, "o", color="tab:red", label=f"{cutoff_frequency:.3g} Hz")
    axis.set(title=f"AC response - run {run_id}", xlabel="Frequency (Hz)", ylabel="Gain (dB)")
    axis.legend()
    path = output_dir / f"{run_id}_ac.png"
    figure.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(figure)
    outputs.append(path)

    figure, axis = plt.subplots()
    if full:
        plot_time, plot_in, plot_out = time, voltage_in, voltage_out
        region = "full run"
    else:
        plot_time, plot_in, plot_out = steady_time, steady_in, steady_out
        region = "steady state"
    axis.plot(plot_time, plot_in, label="Input")
    axis.plot(plot_time, plot_out, label="Output")
    axis.set(title=f"Transient response ({region}) - run {run_id}", xlabel="Time (s)", ylabel="Voltage (V)")
    axis.legend()
    path = output_dir / f"{run_id}_tran.png"
    figure.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(figure)
    outputs.append(path)

    figure, axis = plt.subplots()
    axis.plot(steady_in, steady_out)
    axis.set(title=f"Transfer curve (steady state) - run {run_id}",
             xlabel="Input voltage (V)", ylabel="Output voltage (V)")
    path = output_dir / f"{run_id}_transfer.png"
    figure.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(figure)
    outputs.append(path)

    fundamental = float(transient_protocol["freq_hz"])
    if fundamental <= 0:
        raise ValueError("transient fundamental frequency must be positive")
    period_count = int((steady_time[-1] - steady_time[0]) * fundamental)
    if period_count < 1:
        raise ValueError("steady-state transient must contain at least one full period")

    window_end = steady_time[-1]
    window_start = window_end - period_count / fundamental
    median_step = float(np.median(np.diff(steady_time)))
    samples_per_period = max(2, int(round(1.0 / (fundamental * median_step))))
    sample_count = period_count * samples_per_period
    sample_rate = samples_per_period * fundamental
    uniform_time = window_start + np.arange(sample_count) / sample_rate
    uniform_output = np.interp(uniform_time, steady_time, steady_out)
    uniform_output -= np.mean(uniform_output)

    spectrum = np.fft.rfft(uniform_output)
    magnitude = np.abs(spectrum) / sample_count
    magnitude[1:] *= 2.0
    if sample_count % 2 == 0:
        magnitude[-1] *= 0.5
    spectrum_dbv = 20.0 * np.log10(np.maximum(magnitude, np.finfo(float).tiny))
    spectrum_frequency = np.fft.rfftfreq(sample_count, d=1.0 / sample_rate)
    max_harmonic = (len(spectrum_dbv) - 1) // period_count
    harmonic_numbers = np.arange(1, max_harmonic + 1)
    harmonic_bins = harmonic_numbers * period_count

    figure, axis = plt.subplots()
    axis.plot(spectrum_frequency, spectrum_dbv)
    axis.scatter(spectrum_frequency[harmonic_bins], spectrum_dbv[harmonic_bins],
                 color="tab:red", zorder=3, label="Harmonics")
    axis.set(title=f"Output spectrum (visual only) - run {run_id}",
             xlabel="Frequency (Hz)", ylabel="Magnitude (dBV)")
    axis.legend()
    path = output_dir / f"{run_id}_spectrum.png"
    figure.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(figure)
    outputs.append(path)

    if show:
        for image_path in outputs:
            webbrowser.open(image_path.resolve().as_uri())
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", nargs="?", help="run directory (defaults to the most recent run)")
    parser.add_argument("--full", action="store_true", help="show the full transient in Figure 2")
    parser.add_argument("--show", action="store_true", help="open the saved PNGs in the default image viewer")
    args = parser.parse_args()

    for path in plot_run(args.run_dir, full=args.full, show=args.show):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
