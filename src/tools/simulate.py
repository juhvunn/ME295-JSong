"""simulate: run a netlist in sandboxed ngspice batch mode.

Netlists must come from trusted templates (build_netlist). As a second line of
defense, check_netlist() rejects directives that can touch the filesystem or a
shell, and only allows a small set of commands inside .control blocks.
"""
from __future__ import annotations

import re
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from src.config import REPO_ROOT, load_config

# Dot-directives that are never allowed anywhere in a netlist.
FORBIDDEN_DIRECTIVES = (".shell", ".system", ".include", ".inc", ".lib", ".exec")

# Commands allowed inside .control ... .endc. Everything else (shell, source,
# load, cd, write, ...) is rejected.
ALLOWED_CONTROL_COMMANDS = {
    "set", "unset", "let", "op", "ac", "dc", "tran", "noise",
    "meas", "measure", "print", "echo", "wrdata", "run", "quit", "exit",
}

RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9]+$")


class UnsafeNetlistError(ValueError):
    pass


@dataclass
class SimResult:
    run_id: str
    run_dir: Path
    netlist_path: Path
    log_path: Path
    returncode: int | None
    timed_out: bool

    @property
    def ok(self) -> bool:
        return not self.timed_out and self.returncode == 0


def check_netlist(netlist: str) -> None:
    """Raise UnsafeNetlistError if the netlist contains a dangerous directive."""
    in_control = False
    for lineno, raw in enumerate(netlist.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("*"):
            continue
        word = line.split()[0].lower()

        if word in FORBIDDEN_DIRECTIVES:
            raise UnsafeNetlistError(f"line {lineno}: forbidden directive {word!r}")
        if word == ".control":
            in_control = True
            continue
        if word == ".endc":
            in_control = False
            continue
        if not in_control:
            continue

        if word not in ALLOWED_CONTROL_COMMANDS:
            raise UnsafeNetlistError(f"line {lineno}: control command {word!r} not allowed")
        if word == "wrdata":
            parts = line.split()
            if len(parts) < 2 or not SAFE_FILENAME_RE.match(parts[1]):
                raise UnsafeNetlistError(f"line {lineno}: wrdata target must be a bare filename")


def new_run_id() -> str:
    return f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"


def simulate(
    netlist: str,
    run_id: str | None = None,
    timeout_s: float | None = None,
    executable: str | None = None,
) -> SimResult:
    """Save netlist to runs/<id>/circuit.cir and run `ngspice -b` with a timeout.

    Output files written by wrdata land in runs/<id>/; the ngspice log goes to logs/<id>.log.
    """
    check_netlist(netlist)

    cfg = load_config()
    run_id = run_id or new_run_id()
    if not RUN_ID_RE.match(run_id):
        raise ValueError(f"invalid run_id {run_id!r}")
    timeout_s = timeout_s if timeout_s is not None else cfg["ngspice"]["timeout_s"]
    executable = executable or cfg["ngspice"]["executable"]

    run_dir = REPO_ROOT / cfg["paths"]["runs_dir"] / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    logs_dir = REPO_ROOT / cfg["paths"]["logs_dir"]
    logs_dir.mkdir(parents=True, exist_ok=True)

    netlist_path = run_dir / "circuit.cir"
    netlist_path.write_text(netlist, encoding="utf-8")
    log_path = logs_dir / f"{run_id}.log"

    try:
        proc = subprocess.run(
            [executable, "-b", "-o", str(log_path), netlist_path.name],
            cwd=run_dir,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout_s,
        )
        returncode, timed_out = proc.returncode, False
    except subprocess.TimeoutExpired:
        returncode, timed_out = None, True

    return SimResult(run_id, run_dir, netlist_path, log_path, returncode, timed_out)


def read_wrdata(path: Path, n_vectors: int) -> tuple[np.ndarray, np.ndarray]:
    """Parse a wrdata text file written with `set wr_singlescale` and `set wr_vecnames`.

    Returns (scale, values) with values shaped (n_points, n_vectors). The vectors
    are assumed real (e.g. db(v(out))); the scale is the first column and any extra
    scale columns (e.g. the zero imaginary part of an AC frequency) are dropped.
    """
    data = np.loadtxt(path, skiprows=1, ndmin=2)
    n_scale_cols = data.shape[1] - n_vectors
    if n_scale_cols < 1:
        raise ValueError(f"{path}: {data.shape[1]} columns, expected > {n_vectors}")
    return data[:, 0], data[:, n_scale_cols:]
