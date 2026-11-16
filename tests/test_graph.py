"""LangGraph agent end to end with the scripted FakeLLM (ngspice, no API calls)."""
import io
import json

import pytest

from pedal_agent.cli import main
from pedal_agent.graph import Agent, RunStore, describe_change, new_run
from pedal_agent.llm import FakeLLM, _decision, default_fake_script
from pedal_agent.prompts import planner_prompts
from pedal_agent.schemas import BlockInstance, Candidate, RunRecord

GOAL = "warm mid-forward overdrive with light breakup"


def only_run(store: RunStore) -> RunRecord:
    files = sorted(store.dir.glob("*.json"))
    assert len(files) == 1
    return RunRecord.model_validate_json(files[0].read_text(encoding="utf-8"))


def script(*planner):
    s = default_fake_script()
    s["planner"] = list(planner)
    return s


def test_cli_fake_run_writes_valid_run_record(tmp_path):
    out = io.StringIO()
    code = main(["run", "--goal", GOAL, "--auto-approve", "--no-feedback", "--llm", "fake",
                 "--runs-dir", str(tmp_path)], out=out)
    assert code == 0
    run = only_run(RunStore(tmp_path))
    assert (run.status, run.stop_reason, run.model_id, run.mode) == ("awaiting_feedback", "all_pass", "fake", "agent")
    assert [(s.agent, s.action) for s in run.steps] == [
        ("tone_analyst", "tone_analyst"), ("human", "human_approve_spec"),
        ("planner", "initial_chain"), ("planner", "swap_block"), ("planner", "adjust_params"),
        ("planner", "adjust_params"), ("planner", "adjust_params"), ("router", "stop")]
    assert run.steps[4].validation_errors and run.steps[4].report is None
    assert run.steps[5].duplicate_of == 4 and run.steps[5].report is None
    assert run.steps[6].title == "drive 0.5 → 0.7"
    assert (run.sims_used, run.best_step, run.topology_changes) == (3, 7, 1)
    assert run.spec.approved and run.best.report.n_pass == 4
    assert all(s.llm is not None for s in run.steps if s.agent in ("tone_analyst", "planner"))
    assert "Stopped: all_pass" in out.getvalue() or "all_pass" in out.getvalue()


def test_paused_run_resumes_from_a_new_process(tmp_path):
    store = RunStore(tmp_path)
    agent = Agent(FakeLLM(), store)
    run = new_run(GOAL, agent.llm)
    assert agent.start(run)["kind"] == "approve_spec"
    assert store.load(run.run_id).status == "awaiting_spec_approval"
    agent.close()

    agent2 = Agent(FakeLLM(script(*default_fake_script()["planner"])), RunStore(tmp_path))  # "another process"
    pending = agent2.resume(run.run_id, {"action": "approve"})
    assert pending["kind"] == "feedback" and pending["stop_reason"] == "all_pass"
    assert agent2.resume(run.run_id, {"action": "accept"}) is None
    agent2.close()
    final = store.load(run.run_id)
    assert (final.status, final.stop_reason, final.steps[-1].action) == ("accepted", "human_accept", "human_accept")


def test_feedback_resumes_planner_with_extra_budget(tmp_path):
    plan = default_fake_script()["planner"] + [
        _decision("adjust_params", [("od_ts808", {"drive": 0.75})], "Feedback asked for a bit more gain.")]
    llm = FakeLLM(script(*plan))
    agent = Agent(llm, RunStore(tmp_path))
    run = new_run(GOAL, llm)
    agent.start(run)
    agent.resume(run.run_id, {"action": "approve"})
    pending = agent.resume(run.run_id, {"action": "feedback", "text": "a little more gain please"})
    agent.close()
    assert pending["kind"] == "feedback"
    final = agent.store.load(run.run_id)
    assert final.sim_budget == 16 and final.sims_used == 4
    assert [s.action for s in final.steps][-3:] == ["human_feedback", "adjust_params", "stop"]
    planner_prompt = llm.calls[-1][1]
    assert "a little more gain please" in planner_prompt


def test_reject_spec_stops_without_planning(tmp_path):
    llm = FakeLLM()
    agent = Agent(llm, RunStore(tmp_path))
    run = new_run(GOAL, llm)
    agent.start(run)
    assert agent.resume(run.run_id, {"action": "reject", "why": "not what I meant"}) is None
    agent.close()
    final = agent.store.load(run.run_id)
    assert (final.status, final.stop_reason, final.sims_used) == ("stopped", "human_review", 0)
    assert [n for n, _ in llm.calls] == ["tone_analyst"]


def test_edited_targets_are_stored(tmp_path):
    llm = FakeLLM(script())  # planner script empty -> stops with an error after approval
    agent = Agent(llm, RunStore(tmp_path))
    run = new_run(GOAL, llm)
    spec = agent.start(run)["spec"]
    spec["targets"][0]["lo"] = 12.0
    assert agent.resume(run.run_id, {"action": "approve", "targets": spec["targets"]}) is None
    agent.close()
    final = agent.store.load(run.run_id)
    assert final.spec.targets[0].lo == 12.0 and final.steps[1].title == "Target spec approved (edited)"
    assert (final.status, final.stop_reason) == ("stopped", "error")
    assert "exhausted" in final.steps[-1].why


def test_baseline_mode_rejects_topology_change(tmp_path):
    llm = FakeLLM(script(
        _decision("initial_chain", [("od_ts808", {"drive": 0.5})], "start"),
        _decision("add_block", [("fuzz_ff_si", {}), ("od_ts808", {"drive": 0.5})], "add fuzz"),
        _decision("adjust_params", [("od_ts808", {"drive": 0.7})], "more drive")))
    agent = Agent(llm, RunStore(tmp_path))
    run = new_run(GOAL, llm, mode="baseline_fixed_topology")
    agent.start(run)
    agent.resume(run.run_id, {"action": "approve"})
    agent.close()
    final = agent.store.load(run.run_id)
    assert "only adjust_params" in final.steps[3].validation_errors[0]
    assert (final.stop_reason, final.sims_used, final.topology_changes) == ("all_pass", 2, 0)


def test_planner_prompt_has_tables_not_waveforms(tmp_path):
    main(["run", "--goal", GOAL, "--auto-approve", "--no-feedback", "--llm", "fake",
          "--runs-dir", str(tmp_path)], out=io.StringIO())
    run = only_run(RunStore(tmp_path))
    run.steps = run.steps[:5]  # as the Planner saw it before step 6
    system, user = planner_prompts(run)
    ctx = json.loads(user)
    assert ctx["latest_result"]["step"] == 4 and ctx["best_so_far"]["step"] == 4
    assert {r["metric"] for r in ctx["latest_result"]["table"]} == {"gain_1k_db", "thd_pct", "ac_peak_hz", "even_odd"}
    assert [a["step"] for a in ctx["last_attempts"]] == [3, 4, 5] and "rejected" in ctx["last_attempts"][2]
    for banned in ('"v_out"', '"t_s"', '"mag_db"', '"plots"', ".subckt", "netlist"):
        assert banned not in user


@pytest.mark.parametrize("prev, new, title", [
    (None, [("od_ts808", {})], "Chose od_ts808"),
    ([("od_ts808", {})], [("od_ts808", {"tone": 0.8})], "tone 0.5 → 0.8"),
    ([("od_ts808", {})], [("fuzz_ff_si", {}), ("od_ts808", {})], "Added fuzz_ff_si"),
    ([("fuzz_ff_si", {}), ("od_ts808", {})], [("od_ts808", {})], "Removed fuzz_ff_si"),
    ([("od_ts808", {})], [("dist_distplus", {})], "Swapped od_ts808 → dist_distplus"),
])
def test_describe_change(prev, new, title):
    c = lambda bs: Candidate(chain=[BlockInstance(block_id=b, params=p) for b, p in bs], rationale="")  # noqa: E731
    assert describe_change(c(prev) if prev else None, c(new)) == title
