"""Backend actions the dashboard may call (docs/DASHBOARD_SPEC.md section 3).

The UI only reads run files and calls these functions. Each action that needs the agent starts a
worker process (`python -m pedal_agent.actions worker ...`) that runs the existing graph until its next
pause (spec approval, feedback) or end, writing runs/<run_id>.json after every step as the CLI does, so
the page can poll the file and a page reload does not stop a run.

One active run at a time: a worker holds runs/active_run.lock (created exclusively) while it works and
removes it when it pauses or ends. Any action that would start a worker is refused while the lock is
held; a lock left by a worker that no longer exists is cleared.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from pedal_agent.config import REPO_ROOT
from pedal_agent.graph import Agent, RunStore, new_run, slug
from pedal_agent.schemas import Project

LOCK_NAME = "active_run.lock"
START_GRACE_S = 60                  # a lock still without a worker pid after this is stale


class Busy(RuntimeError):
    """Another run is active (the lock is held)."""


class WrongState(RuntimeError):
    """The action does not fit the run's status."""


def projects_dir(store: RunStore) -> Path:
    d = store.dir.parent / "projects"           # runs/ -> projects/ next to it
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------- lock ----------
def _lock_path(store: RunStore) -> Path:
    return store.dir / LOCK_NAME


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def active(store: RunStore) -> dict | None:
    """The lock's content ({run_id, pid, since}) if a live worker holds it; a stale lock is removed."""
    p = _lock_path(store)
    try:
        info = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError):
        info = {"pid": -1}
    starting = info.get("pid") == 0 and time.time() - p.stat().st_mtime < START_GRACE_S
    if starting or _alive(int(info.get("pid", -1))):           # pid 0: reserved while the worker starts
        return info
    p.unlink(missing_ok=True)
    return None


def _acquire(store: RunStore, run_id: str, pid: int = 0) -> None:
    active(store)                                             # clears a stale lock
    try:
        fd = os.open(_lock_path(store), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise Busy(f"another run is active: {active(store)}") from None
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"run_id": run_id, "pid": pid, "since": f"{datetime.now():%Y-%m-%d %H:%M:%S}"}, f)


def _set_pid(store: RunStore, run_id: str, pid: int) -> None:
    p = _lock_path(store)
    info = json.loads(p.read_text(encoding="utf-8"))
    if info.get("run_id") == run_id:
        info["pid"] = pid
        p.write_text(json.dumps(info), encoding="utf-8")


def _release(store: RunStore, run_id: str) -> None:
    p = _lock_path(store)
    try:
        if json.loads(p.read_text(encoding="utf-8")).get("run_id") == run_id:
            p.unlink()
    except (FileNotFoundError, json.JSONDecodeError):
        pass


# ---------- worker ----------
def _spawn(store: RunStore, run_id: str, kind: str, answer: dict | None, llm: str) -> None:
    """Take the lock for run_id, then start a worker process that keeps it until it pauses or ends."""
    _acquire(store, run_id)
    cmd = [sys.executable, "-m", "pedal_agent.actions", "worker", run_id, kind, "--llm", llm,
           "--runs-dir", str(store.dir), "--answer", json.dumps(answer or {})]
    log = (REPO_ROOT / "logs")
    log.mkdir(exist_ok=True)
    try:
        with open(log / f"worker-{run_id}.log", "a", encoding="utf-8") as f:
            proc = subprocess.Popen(cmd, cwd=REPO_ROOT, stdout=f, stderr=subprocess.STDOUT,
                                    env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    except Exception:
        _release(store, run_id)
        raise
    _set_pid(store, run_id, proc.pid)


def make_llm(kind: str):
    from pedal_agent.cli import make_llm as cli_make_llm
    return cli_make_llm(kind)


def work(store: RunStore, run_id: str, kind: str, answer: dict, llm: str) -> int:
    """Run the graph until its next pause or end (in the worker process). Releases the lock."""
    from pedal_agent.llm import LLMInfraError
    try:
        agent = Agent(make_llm(llm), store)
        try:
            if kind == "start":
                agent.start(store.load(run_id))
            else:
                agent.resume(run_id, answer)
        finally:
            agent.close()
        return 0
    except LLMInfraError as e:                   # the Agent has marked the run infra_error
        print(f"LLM infrastructure problem: {e}", flush=True)
        return 3
    finally:
        _release(store, run_id)


# ---------- actions (docs/DASHBOARD_SPEC.md section 3) ----------
def create_project(name: str, genre: str | None, describe: str, reference: str | None = None,
                   llm: str = "real", store: RunStore | None = None) -> str:
    """Write the Project, start a run: Tone Analyst -> awaiting_spec_approval. Returns the run id."""
    store = store or RunStore()
    if a := active(store):
        raise Busy(f"another run is active: {a['run_id']}")
    goal = describe.strip() + (f" Reference: {reference.strip()}." if reference and reference.strip() else "")
    if not goal:
        raise ValueError("describe the tone first")
    from pedal_agent.cli import make_llm as cli_make_llm
    probe = cli_make_llm(llm)                     # fails early (e.g. no token) before anything is written
    run = new_run(goal, probe, genre=genre or None)
    pdir = projects_dir(store)
    project_id = slug(name or goal)
    path = pdir / f"{project_id}.json"
    project = Project.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else \
        Project(project_id=project_id, name=name or goal[:40], genre=genre or None, describe=describe,
                reference=reference or None)
    project.run_ids.append(run.run_id)
    run.project_id = project_id
    store.save(run)
    path.write_text(project.model_dump_json(indent=2), encoding="utf-8")
    _spawn(store, run.run_id, "start", None, llm)
    return run.run_id


def _need(store: RunStore, run_id: str, status: str):
    run = store.load(run_id)
    if run.status != status:
        raise WrongState(f"run {run_id} is {run.status}, not {status}")
    return run


def approve_spec(run_id: str, edited_targets: list[dict] | None = None, llm: str = "real",
                 store: RunStore | None = None) -> None:
    store = store or RunStore()
    _need(store, run_id, "awaiting_spec_approval")
    answer = {"action": "approve"} | ({"targets": edited_targets} if edited_targets is not None else {})
    _spawn(store, run_id, "resume", answer, llm)


def reject_spec(run_id: str, why: str = "", llm: str = "real", store: RunStore | None = None) -> None:
    store = store or RunStore()
    _need(store, run_id, "awaiting_spec_approval")
    _spawn(store, run_id, "resume", {"action": "reject", "why": why}, llm)


def send_feedback(run_id: str, text: str, llm: str = "real", store: RunStore | None = None) -> None:
    store = store or RunStore()
    _need(store, run_id, "awaiting_feedback")
    if not text.strip():
        raise ValueError("feedback text is empty")
    _spawn(store, run_id, "resume", {"action": "feedback", "text": text.strip()}, llm)


def accept(run_id: str, llm: str = "real", store: RunStore | None = None) -> None:
    """status = accepted (no LLM call; runs in this process under the lock). Audio: Phase 6."""
    store = store or RunStore()
    _need(store, run_id, "awaiting_feedback")
    _acquire(store, run_id, pid=os.getpid())
    work(store, run_id, "resume", {"action": "accept"}, "fake")   # the accept path makes no LLM call


def render_audio(run_id: str, clip: str):
    raise NotImplementedError("Phase 6")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pedal_agent.actions")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("worker", help="internal: run the graph to its next pause")
    w.add_argument("run_id")
    w.add_argument("kind", choices=["start", "resume"])
    w.add_argument("--llm", choices=["real", "fake"], default="real")
    w.add_argument("--runs-dir")
    w.add_argument("--answer", default="{}")
    args = ap.parse_args(argv)
    store = RunStore(args.runs_dir)
    _set_pid(store, args.run_id, os.getpid())
    return work(store, args.run_id, args.kind, json.loads(args.answer), args.llm)


if __name__ == "__main__":
    raise SystemExit(main())
