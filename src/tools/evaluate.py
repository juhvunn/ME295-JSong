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
