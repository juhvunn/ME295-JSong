"""Phase 3 step 4: subset, runner (no peeking, cost gate, resume) and summary. No API calls."""
from types import SimpleNamespace

import pytest
import yaml

from pedal_agent.config import REPO_ROOT, load_config
from scripts import make_subset, run_benchmark, summarize_benchmark

TARGETS = run_benchmark.load_set("v1")


def test_subset_is_fixed_and_stratified():
    ids = make_subset.choose(TARGETS, 2611)
    assert ids == make_subset.choose(TARGETS, 2611)
    by_id = {t["id"]: t for t in TARGETS}
    gen = [by_id[i]["category"] for i in ids if by_id[i]["source"] == "generated"]
    assert {c: gen.count(c) for c in "ABCD"} == {"A": 2, "B": 4, "C": 4, "D": 1}
    assert sum(by_id[i]["source"] == "hand" for i in ids) == 1
    saved = yaml.safe_load((REPO_ROOT / "benchmarks" / "v1_subset.yaml").read_text(encoding="utf-8"))
    assert saved["seed"] == 2611 and saved["targets"] == ids


def test_only_the_oracle_reads_solutions(monkeypatch):
    def forbidden(version):
        raise AssertionError("solutions read")
    monkeypatch.setattr(run_benchmark, "read_solutions", forbidden)
    for m in ("random_catalog", "random_fixed_topology", "agent", "baseline_fixed_topology"):
        assert len(run_benchmark.plan_runs("v1", m, TARGETS, [1], set())) == len(TARGETS)
    with pytest.raises(AssertionError):
        run_benchmark.plan_runs("v1", "random_fixed_topology_oracle", TARGETS, [1], set())
    # nothing in the package (planners, prompts, graph) refers to the solutions file
    for p in (REPO_ROOT / "pedal_agent").rglob("*.py"):
        assert "_solutions" not in p.read_text(encoding="utf-8"), p


def test_oracle_skips_d_and_hand_targets():
    todo = run_benchmark.plan_runs("v1", "random_fixed_topology_oracle", TARGETS, [1, 2], set())
    ids = {t["id"] for t, _, _ in todo}
    assert ids == {t["id"] for t in TARGETS if t["source"] == "generated" and t["category"] != "D"}
    assert all(chain for _, _, chain in todo) and len(todo) == 2 * len(ids)


def test_real_llm_needs_typed_yes_and_makes_no_call_otherwise(monkeypatch, tmp_path, capsys):
    import pedal_agent.llm as llm_mod

    def no_client(*a, **k):
        raise AssertionError("AnthropicLLM constructed")
    monkeypatch.setattr(llm_mod, "AnthropicLLM", no_client)
    monkeypatch.setattr(run_benchmark, "code_version", lambda: ("c" * 40, False))   # as if committed
    rc = run_benchmark.main(["--method", "agent", "--llm", "real", "--targets", "G01", "--seeds", "2",
                             "--out", str(tmp_path)], input_fn=lambda _: "no")
    out = capsys.readouterr().out
    assert rc == 1 and "Estimated cost" in out and "no API call made" in out
    assert not list(tmp_path.glob("*.json"))


def test_cost_estimate_uses_config():
    cfg = load_config()
    llm, b = cfg["llm"], cfg["benchmark"]
    per_call = (b["est_input_tokens_per_call"] * llm["price_in_per_mtok"] +
                b["est_output_tokens_per_call"] * llm["price_out_per_mtok"]) / 1e6
    exp, worst = run_benchmark.cost_estimate(10, cfg)
    assert exp == pytest.approx(10 * (cfg["run"]["sim_budget"] - 1) * per_call)
    assert worst == pytest.approx(10 * 2 * cfg["run"]["sim_budget"] * per_call) and worst > exp


def test_cumulative_success_and_tables():
    R = lambda ok, sims: SimpleNamespace(stop_reason="all_pass" if ok else "budget", sims_used=sims)  # noqa: E731
    runs = [R(True, 1), R(True, 3), R(False, 12), R(True, 12)]
    c = summarize_benchmark.cumulative(runs, 12)
    assert c[0] == 0.25 and c[2] == 0.5 and c[10] == 0.5 and c[11] == 0.75 and len(c) == 12
    groups = {"A": {"random_catalog": runs}, "All": {"random_catalog": runs}}
    table = "\n".join(summarize_benchmark.success_table("t", groups, ["random_catalog"]))
    assert "| A | 75 % (3/4) |" in table


def test_defaults_flag_file_and_c_split():
    flags = yaml.safe_load((REPO_ROOT / "benchmarks" / "v1_solutions_analysis.yaml").read_text(encoding="utf-8"))["targets"]
    assert set(flags) == {t["id"] for t in TARGETS if t["source"] == "generated" and t["category"] != "D"}
    dp = {tid: v["passes_at_defaults"] for tid, v in flags.items()}
    R = lambda tid, mode, ok: SimpleNamespace(  # noqa: E731
        benchmark=SimpleNamespace(target_id=tid, category="C"), mode=mode, stop_reason="all_pass" if ok else "budget")
    yes = next(t for t, v in dp.items() if v and flags[t]["category"] == "C")
    no = next(t for t, v in dp.items() if not v and flags[t]["category"] == "C")
    runs = [R(yes, "random_catalog", True), R(yes, "random_catalog", False), R(no, "random_catalog", False)]
    table = "\n".join(summarize_benchmark.c_split_table("t", runs, ["random_catalog"], dp))
    assert f"| chain at defaults passes ({yes}) | 50 % (1/2) |" in table
    assert f"| needs tuning ({no}) | 0 % (0/1) |" in table


@pytest.mark.slow
def test_runner_writes_records_resumes_and_summarizes(tmp_path):
    for m, extra in (("random_catalog", []), ("random_fixed_topology_oracle", []), ("agent", ["--llm", "fake"])):
        out = tmp_path / "runs" / m
        assert run_benchmark.main(["--method", m, "--targets", "G01,H1", "--seeds", "1", "--out", str(out), *extra]) == 0
        recs = [p for p in out.glob("*.json")]
        assert len(recs) == (1 if m == "random_fixed_topology_oracle" else 2)     # oracle: no hand target
        assert run_benchmark.finished(out) and run_benchmark.plan_runs(
            "v1", m, run_benchmark.select_targets(TARGETS, "G01,H1", "v1"), [1], run_benchmark.finished(out)) == []
    res = tmp_path / "results"
    assert summarize_benchmark.main([str(tmp_path / "runs"), "--out", str(res)]) == 0
    text = (res / "summary.md").read_text(encoding="utf-8")
    assert "Full set" in text and "Subset view" in text and "random catalog" in text and "oracle" in text
    for f in ("per_target.csv", "success_vs_sims.csv", "success_vs_sims.png"):
        assert (res / f).stat().st_size > 0
    runs = summarize_benchmark.load_runs(tmp_path / "runs")
    assert {r.mode for r in runs} == {"random_catalog", "random_fixed_topology_oracle", "agent"}
    assert all(r.model_id in ("none", "fake") and r.cost_usd == 0 for r in runs)
    assert all(r.code_commit and len(r.code_commit) == 40 and r.code_dirty is not None for r in runs)
    assert "Code commits per method" in text and "Block order, full set" in text


SUBSET = run_benchmark.select_targets(TARGETS, "subset", "v1")
S_REPEATS = "A=3,B=5,C=5,D=2,hand=3"


def test_repeats_per_category_on_the_subset():
    reps = run_benchmark.parse_repeats(S_REPEATS)
    seeds = run_benchmark.seeds_per_target(SUBSET, 1, 99, reps)
    by = {t["id"]: t for t in SUBSET}
    for tid, s in seeds.items():
        t = by[tid]
        assert s == list(range(1, 1 + reps["hand" if t["source"] == "hand" else t["category"]]))
    todo = run_benchmark.plan_runs("v1", "agent", SUBSET, seeds, set())
    assert len(todo) == 2 * 3 + 4 * 5 + 4 * 5 + 1 * 2 + 1 * 3 == 51
    assert len(run_benchmark.plan_runs("v1", "agent", SUBSET, seeds, {("G18", 1), ("G18", 2)})) == 49   # resume
    assert run_benchmark.seeds_per_target(SUBSET, 1, 4, None)["G18"] == [1, 2, 3, 4]               # --seeds as before
    assert run_benchmark.seeds_per_target(SUBSET, 1, 4, {"B": 2})["G18"] == []                      # missing key = 0
    with pytest.raises(SystemExit):
        run_benchmark.parse_repeats("A=3,X=2")


def test_real_batch_refused_when_code_is_modified(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(run_benchmark, "code_version", lambda: ("c" * 40, True))
    rc = run_benchmark.main(["--method", "agent", "--llm", "real", "--targets", "subset", "--repeats", S_REPEATS,
                             "--out", str(tmp_path)], input_fn=lambda _: pytest.fail("gate must not be reached"))
    assert rc == 1 and "Refusing a real-LLM batch" in capsys.readouterr().out


def test_wilson_interval():
    lo, hi = summarize_benchmark.wilson(10, 20)
    assert lo == pytest.approx(0.299, abs=1e-3) and hi == pytest.approx(0.701, abs=1e-3)
    assert summarize_benchmark.wilson(0, 20)[0] == 0 and summarize_benchmark.wilson(0, 20)[1] == pytest.approx(0.161, abs=1e-3)


def test_block_order_table():
    def step(chain):
        return SimpleNamespace(report=object(), candidate=SimpleNamespace(chain=[SimpleNamespace(block_id=b) for b in chain]))
    R = lambda tid, *chains: SimpleNamespace(  # noqa: E731
        mode="agent", benchmark=SimpleNamespace(target_id=tid, category="C"), steps=[step(c) for c in chains])
    runs = [R("G25", ["od_ts808"], ["dist_distplus", "od_ts808"], ["od_ts808", "dist_distplus"]),   # both orders
            R("G25", ["od_ts808"], ["dist_distplus", "od_ts808"]),                                   # reversed only
            R("G25", ["od_ts808"])]
    rows = "\n".join(summarize_benchmark.order_table(runs, ["agent"], {"G25": "od_ts808 -> dist_distplus"}, "t"))
    assert "| agent | 3 | 2 | 1 | 3 | 1 | 1 |" in rows
