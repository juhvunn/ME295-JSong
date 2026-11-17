"""Reachability check for benchmark labels (scripts/reachability.py) and relabelled summaries. No simulations."""
import random
from types import SimpleNamespace

import yaml

from pedal_agent.config import REPO_ROOT
from scripts import reachability as R
from scripts import summarize_benchmark


def test_label_uses_the_generator_evidence_rules():
    assert R.label(["dist_distplus"], {"od_ts808", "dist_distplus"}) == "A"     # start chain reachable
    assert R.label(["od_ts808"], set()) == "A"                                  # solution is the start chain
    assert R.label(["dist_distplus"], set()) == "B"                             # other single-block solution
    assert R.label(["od_ts808", "dist_distplus"], {"fuzz_ff_si"}) == "B"         # some other single block passes
    assert R.label(["od_ts808", "dist_distplus"], set()) == "C"


def test_grid_and_samples_cover_the_full_knob_range_deterministically():
    g = R.grid("od_ts808")
    assert len(g) == 3 ** 3 * 3 * 3 * 3                       # knobs {0, .5, 1}^3 x D_clip x C3 x C4 {min, default, max}
    assert {p["drive"] for p in g} == {0.0, 0.5, 1.0} and {p["C4"] for p in g} == {2.2e-11, 5.1e-11, 2.2e-10}
    assert "ge" not in {p["D_clip"] for p in R.grid("dist_distplus")}            # unvalidated choice excluded
    rng1, rng2 = random.Random(R.SEED), random.Random(R.SEED)
    assert [R.random_params("od_ts808", rng1) for _ in range(5)] == [R.random_params("od_ts808", rng2) for _ in range(5)]


def test_neighbours_stay_in_range_and_on_the_series():
    p = {"drive": 1.0, "tone": 0.0, "level": 0.5, "D_clip": "si", "C3": 2.2e-07, "C4": 2.2e-11}
    ns = R.neighbours("od_ts808", p, 0.2)
    assert all(0.0 <= n[k] <= 1.0 for n in ns for k in ("drive", "tone", "level"))
    assert {n["D_clip"] for n in ns} == {"si", "led", "none"}
    assert {n["C3"] for n in ns} == {2.2e-07, 1.5e-07} and {n["C4"] for n in ns} == {2.2e-11, 2.4e-11}


def test_score_matches_the_checker_formula():
    tg = [{"name": "gain_1k_db", "lo": 10.0, "hi": 20.0}, {"name": "thd_pct", "lo": None, "hi": 5.0}]
    assert R.score({"gain_1k_db": 15.0, "thd_pct": 4.0}, tg) == 0
    assert abs(R.score({"gain_1k_db": 8.0, "thd_pct": 6.0}, tg) - (0.2 + 0.2)) < 1e-12


def test_summary_relabels_in_memory_only(tmp_path, monkeypatch):
    bdir = tmp_path / "benchmarks"
    bdir.mkdir()
    for f in ("v1.yaml", "v1_subset.yaml", "v1_solutions_analysis.yaml"):
        (bdir / f).write_text((REPO_ROOT / "benchmarks" / f).read_text(encoding="utf-8"), encoding="utf-8")
    (bdir / "v1_labels_check.yaml").write_text(yaml.safe_dump({"targets": {"G18": {"new": "A"}, "G08": {"new": "B"}}}),
                                               encoding="utf-8")
    monkeypatch.setattr(summarize_benchmark, "B", bdir)
    run = SimpleNamespace(benchmark=SimpleNamespace(set="v1", target_id="G18", category="C"), mode="agent",
                          stop_reason="all_pass", sims_used=4, sim_budget=12, code_commit=None, code_dirty=None,
                          steps=[], seed=1, llm_usage=[], wall_s=1.0)
    monkeypatch.setattr(summarize_benchmark, "load_runs", lambda root, infra=None: [run])
    monkeypatch.setattr(summarize_benchmark, "details_table", lambda *a: [])
    monkeypatch.setattr(summarize_benchmark, "plot", lambda *a, **k: None)
    out = tmp_path / "res"
    assert summarize_benchmark.main([str(tmp_path), "--labels", "checked", "--out", str(out)]) == 0
    text = (out / "summary.md").read_text(encoding="utf-8")
    assert "changed: G18 C→A." in text and "| A | 100 % (1/1)" in text
    assert "| G18 | A |" in text
