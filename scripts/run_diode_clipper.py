"""Run AC and transient analyses of the diode clipper and summarize the results."""
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import REPO_ROOT, load_config  # noqa: E402
from src.tools.build import build_netlist  # noqa: E402
from src.tools.simulate import read_wrdata, simulate  # noqa: E402


def main() -> int:
    cfg = load_config()
    with open(REPO_ROOT / cfg["protocol"], encoding="utf-8") as f:
        proto = yaml.safe_load(f)
    ac, tr = proto["ac"], proto["transient"]

    netlist = build_netlist("diode_clipper.cir", {
        "R1": 4.7e3, "C1": 10e-9,
        "VIN_AMP": tr["amplitude_v"], "FREQ": tr["freq_hz"],
        "AC_PPD": ac["points_per_decade"], "AC_FSTART": ac["f_start_hz"], "AC_FSTOP": ac["f_stop_hz"],
        "TSTEP": tr["t_step_s"], "TSTOP": tr["t_stop_s"],
    })
    res = simulate(netlist)
    print(f"run {res.run_id}: returncode={res.returncode} timed_out={res.timed_out}")
    print(f"  netlist: {res.netlist_path}\n  log:     {res.log_path}")
    if not res.ok:
        print("simulation failed; see log")
        return 1

    freq, gain_db = read_wrdata(res.run_dir / "ac.txt", n_vectors=1)
    t, v = read_wrdata(res.run_dir / "tran.txt", n_vectors=2)
    steady = t >= tr["settle_s"]
    v_in, v_out = v[steady, 0], v[steady, 1]

    print(f"AC: {len(freq)} points, {freq[0]:.3g}-{freq[-1]:.3g} Hz, "
          f"gain {gain_db[0, 0]:.2f} dB @ {freq[0]:.3g} Hz, {gain_db[-1, 0]:.2f} dB @ {freq[-1]:.3g} Hz")
    print(f"TRAN: {len(t)} points; steady-state peak in {np.max(np.abs(v_in)):.3f} V, "
          f"peak out {np.max(np.abs(v_out)):.3f} V")
    return 0


if __name__ == "__main__":
    sys.exit(main())
