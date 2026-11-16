"""Dashboard data layer (read-only, no simulations): example run, block library, benchmark-run index."""
import json

from dashboard import data
from pedal_agent.config import REPO_ROOT

EXAMPLE = REPO_ROOT / "runs" / "example-jazz-christmas.json"


def test_index_lists_the_example_run(tmp_path):
    (tmp_path / "example.json").write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "checkpoints.sqlite").write_text("x")
    (tmp_path / "not_a_run.json").write_text(json.dumps({"hello": 1}))
    idx = data.build_index(tmp_path)
    assert len(idx) == 1
    e = idx[0]
    assert e["chain"] != "–" and 0 <= e["n_pass"] <= e["n_targets"] and e["name"]


def test_index_cache_rereads_only_changed_files(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "a.json").write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    cache = tmp_path / "results" / "index.json"
    first = data.build_index(runs, cache)
    calls = []
    real = data.index_entry
    monkeypatch.setattr(data, "index_entry", lambda p: calls.append(p) or real(p))
    assert data.build_index(runs, cache) == first and calls == []          # served from the cache
    (runs / "b.json").write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    assert len(data.build_index(runs, cache)) == 2 and [p.name for p in calls] == ["b.json"]


def test_panels_from_the_example_run():
    run = data.load_run(EXAMPLE)
    step = data.display_step(run)
    assert step is not None and step.n == run.best_step
    h = data.header(run, step)
    assert h["badge"].startswith(f"{h['n_pass']} of {h['n_targets']} targets met - ")
    cards = data.chain_cards(step)
    assert [c["block_id"] for c in cards] == [b.block_id for b in step.candidate.chain]
    rows = data.target_rows(run, step)
    assert len(rows) == len(run.spec.targets)
    assert all(r["status"] in ("Pass", "Too low", "Too high", "Not measured") for r in rows)
    assert sum(r["status"] == "Pass" for r in rows) == step.report.n_pass
    choices = data.design_choices(run)
    assert [c["n"] for c in choices] == [s.n for s in run.steps]
    panel = data.agent_panel(run)
    assert panel["sims"] == f"{run.sims_used} / {run.sim_budget}" and panel["topology_changes"] == run.topology_changes
    assert data.display_step(run, n=-99) is None


def test_component_list_matches_the_generated_circuit():
    rows = data.components("od_ts808", {"drive": 0.9, "D_clip": "led"})
    by = {r["designator"]: r for r in rows}
    assert by["R9"]["value"] == "10 kΩ" and not by["R9"]["adjustable"]
    assert by["R19"]["adjustable"] and by["R19"]["parameter"] == "drive"
    assert by["R20A"]["parameter"] == "tone" and by["R20B"]["adjustable"]
    assert by["C3"]["parameter"] == "C3" and by["C3"]["value"] == "47 nF"
    assert "D3" in by and by["D3"]["parameter"] == "D_clip" and "D1" not in by     # LED pair chosen
    assert by["X1A"]["kind"] == "Op-amp" and by["X1A"]["value"] == "JRC4558_HALF"
    fuzz = {r["designator"]: r for r in data.components("fuzz_ff_si", {})}
    assert fuzz["Q1"]["parameter"] == "Q_model" and fuzz["R5"]["parameter"] == "R5"


def test_library_grouped_by_category():
    lib = data.library()
    assert list(lib) == ["overdrive", "distortion", "fuzz"]
    od = lib["overdrive"][0]
    assert od["block_id"] == "od_ts808" and od["source"] == "GGG ITS8" and od["character"].endswith(".")


def test_repeated_runs_groups_same_spec_and_mode():
    base = {"spec_key": "k", "mode": "random_catalog"}
    idx = [dict(base, stop_reason="all_pass", sims_used=3), dict(base, stop_reason="budget", sims_used=12),
           dict(base, stop_reason="all_pass", sims_used=5), dict(base, mode="agent", stop_reason="all_pass", sims_used=1)]
    rep = data.repeated_runs(idx, idx[0])
    assert rep["runs"] == 3 and rep["successes"] == 2 and rep["median_sims_to_success"] == 4
    assert data.repeated_runs(idx, idx[3]) is None


def test_eng_format():
    assert data.eng(4700, "Ω") == "4.7 kΩ" and data.eng(4.7e-8, "F") == "47 nF" and data.eng(1.5e6, "Ω") == "1.5 MΩ"
