"""Error handling in runs (incident 2026-11-16, file-save PermissionError during the 20-seed benchmark run).

infra_error (exceptions outside the method) is re-run and left out of results; LLM output failures
("error"), simulation timeouts and ngspice failures are method outcomes: they use budget and count as failures.
ngspice is replaced by a stand-in here, so no real simulations run."""
import pytest

import pedal_agent.checker as checker
import pedal_agent.graph as graph
from pedal_agent.baselines.planners import RandomFixedTopologyPlanner
from pedal_agent.graph import Agent, RunStore, new_benchmark_run
from pedal_agent.llm import FakeLLM
from pedal_agent.schemas import BenchmarkRef, BlockInstance, MetricTarget, TargetSpec
from pedal_agent.tools.simulate import SimResult
from scripts import run_benchmark, summarize_benchmark

SPEC = TargetSpec(goal_text="t", targets=[MetricTarget(name="gain_1k_db", lo=10, label="gain")])
REF = BenchmarkRef(set="v1", target_id="G01", category="A", start_chain=[BlockInstance(block_id="od_ts808")])


def fake_ngspice(tmp_path, timed_out):
    """Stand-in for tools.simulate.simulate: a timeout, or a failed run (returncode 1) with no output files."""
    def run(netlist):
        d = tmp_path / "sim"
        d.mkdir(exist_ok=True)
        return SimResult("x", d, d / "circuit.cir", d / "log", None if timed_out else 1, timed_out)
    return run


def run_with(tmp_path, planner, monkeypatch, timed_out=True):
    monkeypatch.setattr(checker, "run_ngspice", fake_ngspice(tmp_path, timed_out))
    store = RunStore(tmp_path / "runs")
    agent = Agent(planner, store)
    run = new_benchmark_run(SPEC, REF, planner, mode="random_fixed_topology", seed=1)
    try:
        agent.start(run)
    finally:
        agent.close()
    return store, store.load(run.run_id)


def test_save_retries_a_locked_file(tmp_path, monkeypatch):
    store = RunStore(tmp_path)
    run = new_benchmark_run(SPEC, REF, FakeLLM({}), seed=1)
    real, calls = graph.os.replace, []

    def flaky(a, b):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError(5, "Access is denied")
        real(a, b)
    monkeypatch.setattr(graph.os, "replace", flaky)
    store.save(run, pause_s=0)
    assert len(calls) == 3 and store.load(run.run_id).run_id == run.run_id

    monkeypatch.setattr(graph.os, "replace", lambda a, b: (_ for _ in ()).throw(PermissionError(5, "denied")))
    with pytest.raises(PermissionError):
        store.save(run, pause_s=0)


@pytest.mark.parametrize("timed_out", [True, False], ids=["sim_timeout", "ngspice_failure"])
def test_simulation_failures_use_budget_and_count_as_failures(tmp_path, monkeypatch, timed_out):
    store, rec = run_with(tmp_path, RandomFixedTopologyPlanner(1, ["od_ts808"]), monkeypatch, timed_out)
    assert (rec.stop_reason, rec.sims_used) == ("budget", 12)            # every failed simulation used budget
    reports = [s.report for s in rec.steps if s.report]
    assert len(reports) == 12 and all(not r.dc_ok and r.score == float("inf") for r in reports)
    assert all(f"timed_out={timed_out}" in r.errors[0] for r in reports)
    assert run_benchmark.finished(store.dir) == {("G01", 1)}               # an outcome: not re-run
    runs = summarize_benchmark.load_runs(store.dir)
    assert len(runs) == 1 and not summarize_benchmark.success(runs[0])     # counted as a failure


def test_llm_output_failure_is_a_method_outcome(tmp_path, monkeypatch):
    store, rec = run_with(tmp_path, FakeLLM({"planner": []}), monkeypatch)   # no valid planner output
    assert rec.stop_reason == "error" and rec.sims_used == 1                # start step only
    assert run_benchmark.finished(store.dir) == {("G01", 1)}
    assert len(summarize_benchmark.load_runs(store.dir)) == 1


def test_exception_outside_the_method_is_infra_error_and_rerun(tmp_path, monkeypatch):
    class Broken(RandomFixedTopologyPlanner):
        def generate(self, *a):
            raise OSError("disk went away")
    with pytest.raises(OSError):
        run_with(tmp_path, Broken(1, ["od_ts808"]), monkeypatch)
    store = RunStore(tmp_path / "runs")
    [rec] = [store.load(p.stem) for p in store.dir.glob("*.json")]
    assert rec.stop_reason == "infra_error" and "disk went away" in rec.steps[-1].why
    assert run_benchmark.finished(store.dir) == set()                       # re-run on resume
    infra = []
    assert summarize_benchmark.load_runs(store.dir, infra) == [] and len(infra) == 1
