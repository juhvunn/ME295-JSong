"""Benchmark set v1 (Phase 3 step 3): structure, evidence rules, hand targets unchanged, solutions pass.
(Tests may read the solutions file; planners, baselines and the runner may not.)"""
import pytest
import yaml

from pedal_agent.build import load_block
from pedal_agent.checker import check
from pedal_agent.config import REPO_ROOT
from pedal_agent.schemas import BlockInstance, Candidate, MetricTarget, TargetSpec
from pedal_agent.validate import unvalidated

B = REPO_ROOT / "benchmarks"
SET = yaml.safe_load((B / "v1.yaml").read_text(encoding="utf-8"))
SOL = yaml.safe_load((B / "v1_solutions.yaml").read_text(encoding="utf-8"))
HAND = yaml.safe_load((B / "v1_hand_targets.yaml").read_text(encoding="utf-8"))["targets"]
TARGETS = SET["targets"]


def spec(t):
    return TargetSpec(goal_text=t["label"], targets=[MetricTarget(**x) for x in t["targets"]])


def passes(metrics, t):
    return all((x["lo"] is None or metrics[x["name"]] >= x["lo"]) and (x["hi"] is None or metrics[x["name"]] <= x["hi"])
               for x in t["targets"])


def test_header_complete():
    h = SET["header"]
    assert h["version"] == "v1" and isinstance(h["seed"], int) and len(h["git_commit"]) == 40
    assert [f["path"] for f in h["model_files"]] == ["models/opamps.lib", "models/diodes_fitted.lib", "models/bjts_fitted.lib"]
    assert all(len(f["sha256"]) == 64 and f["status"] == "validated" for f in h["model_files"])
    assert h["start_chain"] == ["od_ts808"] and "eligibility" in h["rules"] and "sampling" in h["rules"]


def test_ids_categories_and_specs():
    ids = [t["id"] for t in TARGETS]
    assert len(ids) == len(set(ids)) == 36
    gen = [t for t in TARGETS if t["source"] == "generated"]
    assert {c: sum(t["category"] == c for t in gen) for c in "ABCD"} == {"A": 7, "B": 9, "C": 10, "D": 4}
    assert sorted(t["id"] for t in TARGETS if t["source"] == "hand") == [f"H{i}" for i in range(1, 7)]
    for t in TARGETS:
        spec(t)


def test_evidence_matches_category_rules():
    for t in TARGETS:
        ev, cat = t["evidence"], t["category"]
        assert set(ev["single_blocks"]) == {"od_ts808", "dist_distplus", "fuzz_ff_si"}
        assert ev["start_chain"][0] >= 200 and ev["pool_all"][0] >= 1400        # most of 250 / 1750 draws simulate
        if cat == "A":
            assert ev["start_chain"][1] > 0 or [b["block_id"] for b in SOL[t["id"]]["chain"]] == ["od_ts808"]
        else:
            assert ev["start_chain"][1] == 0, t["id"]
        if cat == "C":
            assert all(v[1] == 0 for v in ev["single_blocks"].values()), t["id"]
        if cat == "D":
            assert ev["pool_all"][1] == 0 and "chain" not in SOL.get(t["id"], {}), t["id"]


def test_solutions_use_validated_choices_only():
    for tid, s in SOL.items():
        if "chain" not in s:                     # hand target without a pool solution (category D)
            continue
        assert 1 <= len(s["chain"]) <= 2
        for b in s["chain"]:
            _, meta = load_block(b["block_id"])
            for name, v in b["params"].items():
                spec_ = meta["params"][name]
                if spec_["type"] == "choice":
                    assert not unvalidated(spec_, v), (tid, name, v)


def test_floors_and_calibration():
    from scripts.make_benchmarks import EO_THD_MIN, FACTORS, OUT_PK_MIN, TARGET_HIT, THD_MIN
    for t in TARGETS:
        names = [x["name"] for x in t["targets"]]
        if t["source"] == "generated" and t["category"] != "D":
            m, c = SOL[t["id"]]["metrics"], t["calibration"]
            assert m["out_pk_v"] >= OUT_PK_MIN, t["id"]
            assert "thd_pct" not in names or m["thd_pct"] >= THD_MIN, t["id"]
            assert "even_odd" not in names or m["thd_pct"] >= EO_THD_MIN, t["id"]
            assert 3 <= len(names) <= 4 and c["factor"] in FACTORS
            assert c["hit_rate"] >= TARGET_HIT and not c["capped"], t["id"]     # capped targets are redrawn
            assert SOL[t["id"]]["calibration"]["hit_rate"] == c["hit_rate"]
        if t["category"] == "D" and t["source"] == "generated":
            assert all(x["hi"] is None or x["hi"] >= THD_MIN for x in t["targets"] if x["name"] == "thd_pct")


def test_hand_targets_unchanged():
    by_id = {t["id"]: t for t in TARGETS}
    for h in HAND:
        got = [(x["name"], x["lo"], x["hi"]) for x in by_id[h["id"]]["targets"]]
        assert got == [(x["name"], x.get("lo"), x.get("hi")) for x in h["targets"]]


def test_start_defaults_solve_no_generated_target():
    m = check(Candidate(chain=[BlockInstance(block_id="od_ts808")], rationale=""), TargetSpec(goal_text="", targets=[])).metrics
    assert not any(passes(m, t) for t in TARGETS if t["source"] == "generated")


@pytest.mark.parametrize("cat", ["A", "B", "C"])
def test_one_solution_per_category_passes(cat):
    t = next(t for t in TARGETS if t["source"] == "generated" and t["category"] == cat)
    s = SOL[t["id"]]
    cand = Candidate(chain=[BlockInstance(block_id=b["block_id"], params=b["params"]) for b in s["chain"]], rationale="")
    rep = check(cand, spec(t))
    assert rep.dc_ok and all(r.status == "pass" for r in rep.results), (t["id"], rep.results)
