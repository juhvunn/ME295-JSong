"""Demo sound (Phase 6): a DI clip through the accepted design, simulated by ngspice (transient at the clip's rate).

Clips: every WAV in audio/ (config audio.clips_dir; PEDAL_CLIPS_DIR overrides it, e.g. for tests): mono, 44.1 or
48 kHz, 16/24/32-bit PCM or float. The synthetic test clip synthetic_plucks.wav is generated there on first use by
synth() (fixed parameters, no randomness, so it is the same file every time; gitignored, not committed).
Each clip: the first clip_s seconds, DC removed, 5 ms fade in/out, scaled to input_peak_v peak EMF at the pickup
model. That level is an assumption (the Checker's test sine level); real hard picking can reach about 1 V.
The clip reaches ngspice as a data file that simulate() writes itself and an XSPICE filesource reads (never
.include); the netlist is the Checker's harness (same pickup model, blocks, models, 1 MOhm load) with that source
in place of the test sine. Output: v(out) interpolated onto the clip's sample grid, DC removed. dry.wav and
processed.wav are both normalized to out_dbfs for listening; meta.json keeps the real output level.
Aliasing: with oversample 1 (default) the circuit is simulated at the clip's rate, so output content above half the
sample rate (hard fuzz harmonics) can fold back as aliasing. oversample 2 simulates at twice the rate and low-pass
filters (scipy resample_poly) back to the clip's rate; measured about 1.5x the render time.
Cache: <runs>/audio/<run_id>/<clip>/ for the run's best step and the clip file's SHA-256.

    python -m pedal_agent.audio synth      # (re)writes the synthetic test clip audio/synthetic_plucks.wav
"""
import argparse
import hashlib
import io
import json
import os
import time
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

from pedal_agent.build import load_block, render
from pedal_agent.checker import models_text
from pedal_agent.config import REPO_ROOT, load_config
from pedal_agent.harness import netlist
from pedal_agent.schemas import Candidate, RunRecord
from pedal_agent.tools.simulate import CLIP_SOURCE, read_wrdata, simulate

RATES = (44100, 48000)
FADE_S = 0.005
SYNTH_NAME = "synthetic_plucks.wav"


class ClipError(ValueError):
    """The WAV cannot be used as a clip (stereo, rate, silent, too short)."""


def cfg() -> dict:
    return load_config()["audio"]


def clips_dir() -> Path:
    return Path(os.environ.get("PEDAL_CLIPS_DIR") or REPO_ROOT / cfg()["clips_dir"])


def clips() -> list[Path]:
    """Every WAV in the clips folder; the synthetic test clip is generated there first if it is missing."""
    if not (clips_dir() / SYNTH_NAME).exists():
        synth(clips_dir() / SYNTH_NAME)
    return sorted(p for p in clips_dir().glob("*") if p.suffix.lower() == ".wav")


def oversample() -> int:
    k = int(cfg().get("oversample", 1))
    if k not in (1, 2):
        raise ValueError(f"config audio.oversample must be 1 or 2, not {k}")
    return k


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_clip(path: Path) -> tuple[int, np.ndarray]:
    """(sample rate, volts at the pickup EMF): first clip_s s, DC removed, faded, peak = input_peak_v."""
    fs, d = wavfile.read(path)
    if d.ndim > 1:
        if d.shape[1] != 1:
            raise ClipError(f"{path.name}: {d.shape[1]} channels; export the DI recording as mono")
        d = d[:, 0]
    if fs not in RATES:
        raise ClipError(f"{path.name}: {fs} Hz; use 44100 or 48000 Hz")
    x = d[: int(cfg()["clip_s"] * fs)].astype(np.float64)
    if len(x) < fs // 2:
        raise ClipError(f"{path.name}: shorter than 0.5 s")
    x -= x.mean()
    n = int(FADE_S * fs)
    ramp = np.linspace(0.0, 1.0, n)
    x[:n] *= ramp
    x[-n:] *= ramp[::-1]
    pk = np.abs(x).max()
    if pk == 0:
        raise ClipError(f"{path.name}: silent")
    return fs, x * (cfg()["input_peak_v"] / pk)


def design_netlist(cand: Candidate, fs: int, n: int, k: int = 1) -> str:
    """The Checker's harness netlist with the clip source and a transient at k times the clip's sample rate."""
    blocks = [(render(b.block_id, b.params), load_block(b.block_id)[1]["subckt"]) for b in cand.chain]
    step = 1 / (k * fs)
    ctrl = "\n".join(["set wr_singlescale", "set wr_vecnames",
                      f"tran {step:.10g} {n / fs:.10g} 0 {step:.10g}", "wrdata out.txt v(out)"])
    return netlist(blocks, models_text(cand), cfg()["input_peak_v"], 0, ctrl, source=CLIP_SOURCE)


def write_wav(path: Path, fs: int, x: np.ndarray) -> None:
    wavfile.write(path, fs, np.clip(np.round(x * 32767), -32768, 32767).astype(np.int16))


def folder(runs_dir: Path, run_id: str, clip: Path) -> Path:
    return runs_dir / "audio" / run_id / clip.stem


def _key(run: RunRecord, clip: Path) -> dict:
    step = run.best
    return {"run_id": run.run_id, "step": step.n, "design_sha256": step.report.netlist_sha256,
            "clip": clip.name, "clip_sha256": sha256(clip)}


def rendered(runs_dir: Path, run: RunRecord, clip: Path) -> dict | None:
    """meta.json of this clip for the run's best step if it is current (same design, same clip file), else None.
    A failed render is current too: its meta has an "error"."""
    p = folder(runs_dir, run.run_id, clip) / "meta.json"
    if run.best is None or run.best.report is None or not p.exists():
        return None
    meta = json.loads(p.read_text(encoding="utf-8"))
    key = _key(run, clip) | {"oversample": oversample()}
    return meta if all(meta.get(k) == v for k, v in key.items()) else None


def render_clip(runs_dir: Path, run: RunRecord, clip: Path) -> dict:
    """Simulate one clip through the run's best step; writes dry.wav, processed.wav, meta.json. Returns meta."""
    out = folder(runs_dir, run.run_id, clip)
    out.mkdir(parents=True, exist_ok=True)
    k = oversample()
    meta = _key(run, clip) | {"input_peak_v": cfg()["input_peak_v"], "out_dbfs": cfg()["out_dbfs"], "oversample": k}
    for f in ("dry.wav", "processed.wav"):
        (out / f).unlink(missing_ok=True)
    try:
        fs, x = load_clip(clip)
        t = np.arange(len(x)) / fs
        buf = io.StringIO()
        np.savetxt(buf, np.c_[t, x], fmt="%.9g")
        t0 = time.perf_counter()
        r = simulate(design_netlist(run.best.candidate, fs, len(x), k), clip=buf.getvalue(),
                     timeout_s=cfg()["timeout_s"])
        render_s = time.perf_counter() - t0
        if not r.ok or not (r.run_dir / "out.txt").exists():
            raise RuntimeError(f"ngspice {'timed out' if r.timed_out else f'failed (exit {r.returncode})'}; "
                               f"log {r.log_path}")
        ts, v = read_wrdata(r.run_dir / "out.txt", 1)
        ts, i = np.unique(ts, return_index=True)
        y = np.interp(np.arange(k * len(x)) / (k * fs), ts, v[i, 0])
        if k > 1:
            y = resample_poly(y, 1, k)                       # anti-alias low-pass, back to the clip's rate
        y -= y.mean()
        out_pk = float(np.abs(y).max())
        level = 10 ** (cfg()["out_dbfs"] / 20)
        write_wav(out / "dry.wav", fs, x / np.abs(x).max() * level)
        write_wav(out / "processed.wav", fs, y / out_pk * level if out_pk > 1e-9 else 0 * y)
        meta |= {"fs": fs, "seconds": round(len(x) / fs, 3), "output_peak_v": out_pk,
                 "output_rms_v": float(np.sqrt(np.mean(y ** 2))), "render_s": round(render_s, 1), "sim_id": r.run_id}
    except (ClipError, RuntimeError, OSError, ValueError) as e:
        meta["error"] = str(e)
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def render_all(runs_dir: Path, run: RunRecord, names: list[str] | None = None) -> list[dict]:
    """Render the named clips (default: every clip in audio/) that are not current yet or whose render failed."""
    todo = [c for c in clips() if (names is None or c.name in names)
            and ((m := rendered(runs_dir, run, c)) is None or "error" in m)]
    return [render_clip(runs_dir, run, c) for c in todo]


def level_text(meta: dict) -> str:
    """Real output level of a render, e.g. 'output peak 0.217 V (-13.3 dBV), 0.3 V peak in'."""
    pk = meta["output_peak_v"]
    return (f"output peak {pk:.3g} V ({20 * np.log10(max(pk, 1e-12)):.1f} dBV) at the amp input for "
            f"{meta['input_peak_v']:g} V peak at the pickup")


ASSUMPTION = ("Input assumption: each clip is scaled to {v:g} V peak EMF at the pickup model (the level of the "
              "test sine); real hard picking can reach about 1 V, which would clip harder. Both players are "
              "normalized to {db:g} dBFS for listening.")


ALIASING = {1: "Simulated at the clip's sample rate (no oversampling): output content above half the sample rate "
               "(hard fuzz harmonics) can fold back as aliasing.",
            2: "Simulated at twice the clip's sample rate and low-pass filtered back (2x oversampling), which "
               "limits aliasing from content above half the sample rate."}


def assumption_text() -> str:
    return ASSUMPTION.format(v=cfg()["input_peak_v"], db=cfg()["out_dbfs"])


def aliasing_text() -> str:
    return ALIASING[oversample()]


def synth(path: Path, fs: int = 44100, seconds: float = 8.0) -> Path:
    """Synthetic DI test clip: single plucked notes (E2 A2 D3 G3), then a strummed E major chord; peak -6 dBFS.
    Each note: 15 harmonics plucked at 1/5 of the string length, higher harmonics decaying faster."""
    t = np.arange(int(fs * seconds)) / fs
    x = np.zeros_like(t)
    notes = [(0.0, 82.41), (1.0, 110.0), (2.0, 146.83), (3.0, 196.0)] + \
            [(4.5 + 0.015 * k, f) for k, f in enumerate([82.41, 123.47, 164.81, 207.65, 246.94, 329.63])]
    for start, f0 in notes:
        tt = t - start
        on = tt >= 0
        for n in range(1, 16):
            if n * f0 > 0.45 * fs:
                break
            a = np.sin(np.pi * n / 5) / n ** 1.5
            x[on] += a * np.sin(2 * np.pi * n * f0 * tt[on]) * np.exp(-tt[on] * (1.2 + 0.6 * n))
    x *= 10 ** (-6 / 20) / np.abs(x).max()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_wav(path, fs, x)
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pedal_agent.audio")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("synth", help=f"write the synthetic test clip ({SYNTH_NAME}) into the clips folder")
    s.add_argument("--out")
    args = ap.parse_args(argv)
    print("wrote", synth(Path(args.out) if args.out else clips_dir() / SYNTH_NAME))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
