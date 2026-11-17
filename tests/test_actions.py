"""Dashboard backend actions (pedal_agent/actions.py) with the fake LLM: worker processes, the one-run lock."""
import json
import os
import time

import pytest

from pedal_agent import actions
from pedal_agent.graph import RunStore


def wait_for(store, run_id, statuses, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        run = store.load(run_id)
        if run.status in statuses and actions.active(store) is None:
            return run
        time.sleep(0.5)
    raise AssertionError(f"run {run_id} still {store.load(run_id).status}, lock {actions.active(store)}")


def test_lock_is_exclusive_and_stale_locks_are_cleared(tmp_path):
    store = RunStore(tmp_path / "runs")
    actions._acquire(store, "r1", pid=os.getpid())
    with pytest.raises(actions.Busy):
        actions._acquire(store, "r2")
    assert actions.active(store)["run_id"] == "r1"
    actions._release(store, "r2")                       # someone else's release does nothing
    assert actions.active(store)["run_id"] == "r1"
    actions._release(store, "r1")
    assert actions.active(store) is None
    (store.dir / actions.LOCK_NAME).write_text(json.dumps({"run_id": "dead", "pid": 999999}), encoding="utf-8")
    assert actions.active(store) is None and not (store.dir / actions.LOCK_NAME).exists()     # dead worker
    actions._acquire(store, "r3")                       # pid 0: worker starting, held within the grace time
    assert actions.active(store)["run_id"] == "r3"
    old = time.time() - actions.START_GRACE_S - 5
    os.utime(store.dir / actions.LOCK_NAME, (old, old))
    assert actions.active(store) is None                # never got a worker


def test_create_project_refused_while_another_run_is_active(tmp_path):
    store = RunStore(tmp_path / "runs")
    actions._acquire(store, "other", pid=os.getpid())
    with pytest.raises(actions.Busy):
        actions.create_project("Jazz", "jazz", "warm clean jazz tone", llm="fake", store=store)
    assert not list(store.dir.glob("*.json")) and not (tmp_path / "projects").exists()


def test_actions_check_the_run_status(tmp_path):
    store = RunStore(tmp_path / "runs")
    from pedal_agent.graph import new_run
    from pedal_agent.llm import FakeLLM
    run = new_run("warm", FakeLLM())
    store.save(run)                                     # status running
    for call in (lambda: actions.approve_spec(run.run_id, llm="fake", store=store),
                 lambda: actions.send_feedback(run.run_id, "more gain", llm="fake", store=store),
                 lambda: actions.accept(run.run_id, store=store)):
        with pytest.raises(actions.WrongState):
            call()
    assert actions.active(store) is None


@pytest.mark.slow
def test_live_flow_create_approve_feedback_accept(tmp_path):
    store = RunStore(tmp_path / "runs")
    run_id = actions.create_project("Jazz Christmas", "jazz", "warm, clean jazz tone", "Joe Pass", llm="fake",
                                    store=store)
    project = json.loads((tmp_path / "projects" / "jazz-christmas.json").read_text(encoding="utf-8"))
    assert project["run_ids"] == [run_id] and project["reference"] == "Joe Pass"
    run = wait_for(store, run_id, {"awaiting_spec_approval"})
    assert run.project_id == "jazz-christmas" and run.spec.targets and "Reference: Joe Pass." in run.spec.goal_text
    actions.approve_spec(run_id, llm="fake", store=store)
    run = wait_for(store, run_id, {"awaiting_feedback", "stopped"})
    assert run.status == "awaiting_feedback" and run.sims_used >= 1, run.steps[-1].why
    actions.send_feedback(run_id, "a bit more gain", llm="fake", store=store)
    run = wait_for(store, run_id, {"awaiting_feedback", "stopped"})
    assert any(s.action == "human_feedback" for s in run.steps)
    actions.accept(run_id, store=store)
    run = store.load(run_id)
    assert run.status == "accepted" and run.steps[-1].action == "human_accept" and actions.active(store) is None
