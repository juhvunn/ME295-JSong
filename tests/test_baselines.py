"""AI-free baselines (Phase 3 step 2): sampling rules, determinism, and runs through the same graph."""
import random

import pytest

from pedal_agent.baselines.planners import RandomCatalogPlanner, RandomFixedTopologyPlanner
from pedal_agent.baselines.sampling import sample_design
from pedal_agent.build import load_block, parse_value
from pedal_agent.graph import Agent, RunStore, new_benchmark_run
from pedal_agent.schemas import BenchmarkRef, BlockInstance, MetricTarget, PlannerDecision, TargetSpec
from pedal_agent.validate import series_values, unvalidated, validate

UNREACHABLE = TargetSpec(goal_text="bench", targets=[
    MetricTarget(name="gain_1k_db", lo=40, label="gain"), MetricTarget(name="thd_pct", hi=0.5, label="thd")])


def decisions(planner, n):
    return [planner.generate("planner", "", "", PlannerDecision)[0] for _ in range(n)]


def test_samples_follow_the_rules():
    rng = random.Random(1)
    seen_blocks, seen_lengths = set(), set()
    for _ in range(300):
        design = sample_design(rng)
        ids = [b for b, _ in design]
        seen_blocks |= set(ids)
        seen_lengths.add(len(ids))
        assert 1 <= len(ids) <= 2 and len(set(ids)) == len(ids)
        if "fuzz_ff_si" in ids:
            assert ids[0] == "fuzz_ff_si"
        for b, params in design:
            _, meta = load_block(b)
            assert set(params) == set(meta["params"])
            for name, v in params.items():
                spec = meta["params"][name]
                if spec["type"] == "pot":
                    assert 0.05 <= v <= 0.95
                elif spec["type"] == "choice":
                    assert v in spec["choices"] and not unvalidated(spec, v)      # never D_clip=ge
                else:
                    assert v in series_values(spec["series"], parse_value(spec["min"]), parse_value(spec["max"]))
    assert seen_blocks == {"od_ts808", "dist_distplus", "fuzz_ff_si"} and seen_lengths == {1, 2}


def test_series_values_and_snap_agree():
    vals = series_values("E6", 22e-9, 220e-9)
    assert vals[0] == pytest.approx(22e-9) and vals[-1] == pytest.approx(220e-9) and len(vals) == 7


def test_same_seed_same_decisions_different_seed_different():
    a, b, c = (decisions(RandomCatalogPlanner(s, ["od_ts808"]), 12) for s in (5, 5, 6))
    assert a == b and a != c


def test_catalog_proposals_pass_validate_without_warnings():
    planner, prev = RandomCatalogPlanner(3, ["od_ts808"]), ["od_ts808"]
    for d in decisions(planner, 40):
        res = validate(d.to_candidate(), d.action, prev, mode="random_catalog", allow_unvalidated=False)
        assert res.ok and res.warnings == [] and res.action == d.action
        prev = [b.block_id for b in res.candidate.chain]


def test_fixed_topology_planner_never_changes_the_chain():
    for chain in (["od_ts808"], ["fuzz_ff_si", "od_ts808"]):
        for d in decisions(RandomFixedTopologyPlanner(2, chain), 20):
            assert [b.block_id for b in d.chain] == chain and d.action == "adjust_params"


def run(tmp_path, planner, mode, start):
    agent = Agent(planner, RunStore(tmp_path))
    ref = BenchmarkRef(set="test", target_id="T01", category="C", start_chain=[BlockInstance(block_id=b) for b in start])
    r = new_benchmark_run(UNREACHABLE, ref, planner, mode=mode, seed=11)
    agent.start(r)
    agent.close()
    return agent.store.load(r.run_id)


def test_random_catalog_run(tmp_path):
    rec = run(tmp_path, RandomCatalogPlanner(11, ["od_ts808"]), "random_catalog", ["od_ts808"])
    assert (rec.mode, rec.model_id, rec.seed, rec.stop_reason, rec.sims_used) == ("random_catalog", "none", 11, "budget", 12)
    assert rec.input_tokens == 0 and rec.placeholder_or_unvalidated is False
    assert rec.topology_changes > 0 and all(not s.validation_errors for s in rec.steps)


def test_random_fixed_topology_run(tmp_path):
    rec = run(tmp_path, RandomFixedTopologyPlanner(11, ["od_ts808"]), "random_fixed_topology", ["od_ts808"])
    assert rec.sims_used == 12 and rec.topology_changes == 0
    assert all([b.block_id for b in s.candidate.chain] == ["od_ts808"] for s in rec.steps if s.report)


def test_oracle_run_starts_on_its_own_chain(tmp_path):
    chain = ["fuzz_ff_si", "od_ts808"]
    rec = run(tmp_path, RandomFixedTopologyPlanner(11, chain), "random_fixed_topology_oracle", chain)
    assert rec.steps[1].title == "Benchmark start: fuzz_ff_si → od_ts808 (defaults)"
    assert all([b.block_id for b in s.candidate.chain] == chain for s in rec.steps if s.report)


def test_runs_are_reproducible(tmp_path):
    a = run(tmp_path / "a", RandomCatalogPlanner(4, ["od_ts808"]), "random_catalog", ["od_ts808"])
    b = run(tmp_path / "b", RandomCatalogPlanner(4, ["od_ts808"]), "random_catalog", ["od_ts808"])
    chains = lambda r: [(s.candidate.model_dump(), round(s.report.score, 9)) for s in r.steps if s.report]  # noqa: E731
    assert chains(a) == chains(b)


def test_validate_locks_the_chain_for_random_fixed_modes():
    from pedal_agent.schemas import Candidate
    cand = Candidate(chain=[BlockInstance(block_id="dist_distplus")], rationale="")
    for mode in ("random_fixed_topology", "random_fixed_topology_oracle"):
        res = validate(cand, "swap_block", ["od_ts808"], mode=mode)
        assert not res.ok and "chain must stay ['od_ts808']" in res.errors[0]
