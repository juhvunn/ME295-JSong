"""Validate: deterministic checks before simulation (no ngspice)."""
import pytest

from pedal_agent.schemas import BlockInstance, Candidate
from pedal_agent.validate import fingerprint, snap, validate


def cand(*blocks):
    """cand(("od_ts808", {"drive": 0.7}), "fuzz_ff_si", ...)"""
    chain = [BlockInstance(block_id=b) if isinstance(b, str) else BlockInstance(block_id=b[0], params=b[1])
             for b in blocks]
    return Candidate(chain=chain, rationale="r")


def test_valid_initial_chain():
    res = validate(cand(("od_ts808", {"drive": 0.7, "D_clip": "led"})), "initial_chain", None)
    assert res.ok and res.warnings == []
    assert res.action == "initial_chain"
    assert res.candidate.chain[0].params == {"drive": 0.7, "D_clip": "led"}


@pytest.mark.parametrize("candidate, message", [
    (cand("big_muff"), "unknown block"),
    (cand(("od_ts808", {"drive": 1.5})), "knob position must be in [0, 1]"),
    (cand(("od_ts808", {"C3": 1e-6})), "outside [22n, 220n]"),
    (cand(("od_ts808", {"D_clip": "germanium"})), "not one of"),
    (cand(("od_ts808", {"gain": 0.5})), "unknown parameter"),
    (cand(("od_ts808", {"drive": "lots"})), "expected a number"),
    (cand("od_ts808", "od_ts808"), "at most once"),
    (cand("od_ts808", "dist_distplus", "fuzz_ff_si", ("od_ts808", {})), "1-3 blocks"),
    (Candidate(chain=[], rationale=""), "1-3 blocks"),
])
def test_rejects(candidate, message):
    res = validate(candidate, "initial_chain", None)
    assert not res.ok and res.candidate is None
    assert any(message in e for e in res.errors), res.errors


def test_baseline_mode_rejects_chain_change():
    res = validate(cand("fuzz_ff_si", "od_ts808"), "add_block", ["od_ts808"], mode="baseline_fixed_topology")
    assert not res.ok and "only adjust_params" in res.errors[0]
    ok = validate(cand(("od_ts808", {"drive": 0.9})), "adjust_params", ["od_ts808"], mode="baseline_fixed_topology")
    assert ok.ok and ok.action == "adjust_params"


def test_baseline_mode_allows_any_initial_chain():
    assert validate(cand("fuzz_ff_si", "od_ts808"), "initial_chain", None, mode="baseline_fixed_topology").ok


def test_snaps_components_to_e_series():
    res = validate(cand(("od_ts808", {"C3": 50e-9, "C4": "51p"})), "initial_chain", None)
    assert res.ok
    assert res.candidate.chain[0].params == {"C3": 47e-9, "C4": 51e-12}
    assert res.warnings == ["od_ts808.C3: 5e-08 snapped to 4.7e-08 (E6)"]


def test_snap_stays_in_range():
    assert snap(250e-9, "E6", 22e-9, 220e-9) == pytest.approx(220e-9)
    assert snap(9.9e3, "E12", 4.7e3, 12e3) == pytest.approx(10e3)


def test_fuzz_not_first_is_only_a_warning():
    res = validate(cand("od_ts808", "fuzz_ff_si"), "initial_chain", None)
    assert res.ok
    assert any("fuzz_ff_si is not first" in w for w in res.warnings)
    assert validate(cand("fuzz_ff_si", "od_ts808"), "initial_chain", None).warnings == []


@pytest.mark.parametrize("previous, blocks, expected", [
    (["od_ts808"], ["od_ts808"], "adjust_params"),
    (["od_ts808"], ["fuzz_ff_si", "od_ts808"], "add_block"),
    (["fuzz_ff_si", "od_ts808"], ["od_ts808"], "remove_block"),
    (["od_ts808"], ["dist_distplus"], "swap_block"),
    (["fuzz_ff_si", "od_ts808"], ["od_ts808", "fuzz_ff_si"], "swap_block"),
])
def test_action_is_derived_from_the_chain_change(previous, blocks, expected):
    res = validate(cand(*blocks), "adjust_params", previous)
    assert res.ok and res.action == expected
    relabelled = any("relabelled" in w for w in res.warnings)
    assert relabelled == (expected != "adjust_params")


def test_fingerprint_fills_defaults():
    a = validate(cand("od_ts808"), "initial_chain", None).candidate
    b = validate(cand(("od_ts808", {"drive": 0.5, "D_clip": "si", "C3": "47n"})), "initial_chain", None).candidate
    c = validate(cand(("od_ts808", {"drive": 0.6})), "initial_chain", None).candidate
    assert fingerprint(a) == fingerprint(b) != fingerprint(c)
