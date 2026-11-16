"""Benchmark runs (Phase 3 step 1): pre-approved spec, common start step, benchmark stop rules.
Fake LLM only (no API cost)."""
import json

import pytest

from pedal_agent.checker import check
from pedal_agent.graph import Agent, RunStore, new_benchmark_run
from pedal_agent.llm import FakeLLM, _decision
from pedal_agent.prompts import planner_prompts
from pedal_agent.schemas import BenchmarkRef, BlockInstance, Candidate, MetricTarget, RunRecord, TargetSpec

START = [BlockInstance(block_id="od_ts808")]
UNREACHABLE = TargetSpec(goal_text="bench", targets=[
    MetricTarget(name="gain_1k_db", lo=40, label="gain"), MetricTarget(name="thd_pct", hi=0.5, label="thd")])


def ref(category="B"):
    return BenchmarkRef(set="test", target_id="T01", category=category, start_chain=START)


def run_bench(tmp_path, planner, spec=UNREACHABLE, mode="agent"):
    llm = FakeLLM({"planner": planner})
    agent = Agent(llm, RunStore(tmp_path))
    run = new_benchmark_run(spec, ref(), llm, mode=mode, seed=7)
    pending = agent.start(run)
    agent.close()
    return agent.store.load(run.run_id), llm, pending


def drive(*values):
    return [_decision("adjust_params", [("od_ts808", {"drive": v})], f"drive {v}") for v in values]


def test_pre_approved_spec_and_common_start(tmp_path):
    run, llm, pending = run_bench(tmp_path, drive(0.6))
    assert [n for n, _ in llm.calls][0] == "planner"            # no Tone Analyst call
    s1, s2 = run.steps[0], run.steps[1]
    assert (s1.agent, s1.action) == ("human", "human_approve_spec") and "pre-approved" in s1.title
    assert (s2.agent, s2.action, s2.title) == ("router", "initial_chain", "Benchmark start: od_ts808 (defaults)")
    assert s2.report is not None and s2.candidate.chain[0].params == {}
    assert run.spec.approved and (run.mode, run.seed, run.benchmark.target_id) == ("agent", 7, "T01")
    # the first Planner prompt includes the start step's result
    ctx = json.loads(llm.calls[0][1])
    assert ctx["latest_result"]["step"] == 2 and ctx["last_attempts"][0]["step"] == 2


def test_all_pass_at_the_start_stops_without_planning(tmp_path):
    m = check(Candidate(chain=START, rationale=""), TargetSpec(goal_text="", targets=[])).metrics
    spec = TargetSpec(goal_text="bench", targets=[
        MetricTarget(name="gain_1k_db", lo=m["gain_1k_db"] - 1, hi=m["gain_1k_db"] + 1, label="gain"),
        MetricTarget(name="ac_peak_hz", lo=m["ac_peak_hz"] / 1.25, hi=m["ac_peak_hz"] * 1.25, label="peak")])
    run, llm, pending = run_bench(tmp_path, [], spec=spec)
    assert (run.stop_reason, run.sims_used, llm.calls) == ("all_pass", 1, [])
    assert pending["kind"] == "feedback"


def test_no_stall_or_duplicate_stop_full_budget_used(tmp_path):
    # two duplicates of the start (drive 0.5 = default) in a row, then 11 distinct non-improving settings
    plan = drive(0.5, 0.5) + drive(0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.55, 0.6)
    run, llm, _ = run_bench(tmp_path, plan)
    assert run.stop_reason == "budget" and run.sims_used == 12
    assert [s.duplicate_of for s in run.steps[2:4]] == [2, 2]


def test_planner_call_cap_still_applies(tmp_path):
    bad = drive(*([1.5] * 30))                                  # always rejected by Validate (no sims)
    run, llm, _ = run_bench(tmp_path, bad)
    assert run.stop_reason == "budget" and run.sims_used == 1
    assert sum(s.agent == "planner" for s in run.steps) == 24     # 2 x sim budget


def test_baseline_fixed_topology_is_locked_to_the_start_chain(tmp_path):
    plan = [_decision("initial_chain", [("dist_distplus", {})], "my own start")] + drive(0.7)
    run, llm, _ = run_bench(tmp_path, plan + drive(*[0.1 * k for k in range(1, 10)]), mode="baseline_fixed_topology")
    first = next(s for s in run.steps if s.agent == "planner")
    assert first.validation_errors and "chain must stay ['od_ts808']" in first.validation_errors[0]
    assert all(b.block_id == "od_ts808" for s in run.steps if s.report for b in s.candidate.chain)


def test_benchmark_record_round_trips(tmp_path):
    run, _, _ = run_bench(tmp_path, drive(0.6))
    files = list(RunStore(tmp_path).dir.glob("*.json"))
    again = RunRecord.model_validate_json(files[0].read_text(encoding="utf-8"))
    assert again.benchmark == run.benchmark and again.seed == 7


@pytest.mark.parametrize("mode", ["random_catalog", "random_fixed_topology", "random_fixed_topology_oracle"])
def test_new_mode_names_accepted(mode):
    RunRecord(run_id="r", project_id="p", model_id="none", effort="none", status="running", mode=mode)
