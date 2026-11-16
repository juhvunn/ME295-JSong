"""Router stop rules on hand-made RunRecords (no ngspice, no LLM)."""
import pytest

from pedal_agent.router import RouterConfig, best_step, find_duplicate, route
from pedal_agent.schemas import (BlockInstance, Candidate, CheckReport, MetricResult, RunRecord, Step)

CFG = RouterConfig(sim_budget=12, stall_checks=3, max_planner_calls=24)


def cand(drive):
    return Candidate(chain=[BlockInstance(block_id="od_ts808", params={"drive": drive})], rationale="")


def report(score, statuses=("pass",), dc_ok=True):
    return CheckReport(metrics={}, score=score, dc_ok=dc_ok,
                       results=[MetricResult(name="gain_1k_db", value=0.0, status=s) for s in statuses])


def run_with(*planner):
    """planner: ("check", drive, score[, statuses]) | ("invalid",) | ("dup", n)"""
    steps = [Step(n=1, agent="tone_analyst", action="tone_analyst", title="", why=""),
             Step(n=2, agent="human", action="human_approve_spec", title="", why="")]
    sims = 0
    for p in planner:
        n = len(steps) + 1
        if p[0] == "check":
            statuses = p[3] if len(p) > 3 else ("low",)
            steps.append(Step(n=n, agent="planner", action="adjust_params", title="", why="",
                              candidate=cand(p[1]), report=report(p[2], statuses)))
            sims += 1
        elif p[0] == "invalid":
            steps.append(Step(n=n, agent="planner", action="adjust_params", title="", why="",
                              validation_errors=["bad"]))
        else:
            steps.append(Step(n=n, agent="planner", action="adjust_params", title="", why="",
                              candidate=cand(0.5), duplicate_of=p[1]))
    return RunRecord(run_id="r", project_id="p", model_id="m", effort="e", status="running",
                     steps=steps, sims_used=sims)


def test_continue_while_improving():
    assert route(run_with(("check", 0.5, 0.3), ("check", 0.6, 0.2)), CFG) is None


def test_all_pass():
    assert route(run_with(("check", 0.5, 0.3), ("check", 0.7, 0.0, ("pass", "pass"))), CFG) == "all_pass"


def test_all_pass_requires_dc_ok():
    run = run_with(("check", 0.7, 0.0, ("pass",)))
    run.steps[-1].report.dc_ok = False
    assert route(run, CFG) is None


def test_budget_by_simulations():
    run = run_with(*[("check", 0.1 * i, 1.0 - 0.05 * i) for i in range(12)])
    assert run.sims_used == 12
    assert route(run, CFG) == "budget"


def test_budget_by_planner_calls_safety_net():
    run = run_with(*[("invalid",)] * 24)
    assert run.sims_used == 0
    assert route(run, CFG) == "budget"


def test_stall_after_three_checks_without_improvement():
    base = [("check", 0.5, 0.3), ("check", 0.6, 0.1)]
    assert route(run_with(*base, ("check", 0.7, 0.2), ("check", 0.8, 0.15)), CFG) is None
    assert route(run_with(*base, ("check", 0.7, 0.2), ("check", 0.8, 0.15), ("check", 0.9, 0.1)), CFG) == "stall"


def test_invalid_proposals_do_not_count_as_checks_for_stall():
    run = run_with(("check", 0.5, 0.1), ("invalid",), ("invalid",), ("invalid",))
    assert route(run, CFG) is None


def test_one_duplicate_continues_two_in_a_row_stop():
    assert route(run_with(("check", 0.5, 0.3), ("dup", 3)), CFG) is None
    assert route(run_with(("check", 0.5, 0.3), ("dup", 3), ("check", 0.6, 0.2), ("dup", 3)), CFG) is None
    assert route(run_with(("check", 0.5, 0.3), ("dup", 3), ("dup", 3)), CFG) == "duplicate"


def test_best_step_and_find_duplicate():
    run = run_with(("check", 0.5, 0.3), ("check", 0.6, 0.1), ("check", 0.7, 0.2))
    assert best_step(run).n == 4
    assert find_duplicate(run, cand(0.6)) == 4
    assert find_duplicate(run, cand(0.65)) is None
    # defaults filled in: drive 0.5 == the block default
    assert find_duplicate(run, Candidate(chain=[BlockInstance(block_id="od_ts808")], rationale="")) == 3


def test_config_from_yaml():
    cfg = RouterConfig.from_config()
    assert (cfg.sim_budget, cfg.stall_checks, cfg.max_planner_calls) == (12, 3, 24)
