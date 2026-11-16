"""evaluate: deterministic Checker metrics (gain, AC response, THD)."""
import numpy as np


def f_minus3db(freq: np.ndarray, gain_db: np.ndarray) -> float:
    """Frequency where gain first falls 3 dB below its value at the lowest frequency.

    Interpolates linearly in log10(frequency). Raises ValueError if it never does.
    """
    freq, gain_db = np.asarray(freq, float), np.asarray(gain_db, float)
    target = gain_db[0] - 3.0
    below = np.nonzero(gain_db <= target)[0]
    if below.size == 0 or below[0] == 0:
        raise ValueError("no -3 dB crossing in the swept range")
    i = below[0]
    lf0, lf1 = np.log10(freq[i - 1]), np.log10(freq[i])
    g0, g1 = gain_db[i - 1], gain_db[i]
    return float(10 ** (lf0 + (target - g0) * (lf1 - lf0) / (g1 - g0)))


def check_targets(metrics: dict[str, float | None], targets: list[dict]) -> list[dict]:
    """Compare metrics with targets {"metric", "target", "tol_rel"}.

    Returns one structured row per target: target, got, error (relative), met.
    A metric that could not be measured has got=None, error=None, met=False.
    """
    rows = []
    for spec in targets:
        got = metrics.get(spec["metric"])
        error = None if got is None else (got - spec["target"]) / spec["target"]
        rows.append({
            "metric": spec["metric"],
            "target": spec["target"],
            "got": got,
            "error": error,
            "tol_rel": spec["tol_rel"],
            "met": error is not None and abs(error) <= spec["tol_rel"],
        })
    return rows
