"""The Streamlit page runs without errors (streamlit.testing, no browser, no simulations)."""
import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from dashboard import data  # noqa: E402
from pedal_agent import actions  # noqa: E402
from pedal_agent.config import REPO_ROOT  # noqa: E402

APP = str(REPO_ROOT / "dashboard" / "app.py")


def html(at) -> str:
    return "\n".join(m.value for m in at.markdown)


def test_example_run_page_renders_with_illustrative_badge():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception, at.exception
    example = next(e for e in data.build_index() if "example-jazz-christmas" in e["path"])
    at.radio[1].set_value(example["run_id"]).run()                       # the project list may hold other runs too
    assert not at.exception, at.exception
    text = html(at)
    assert data.ILLUSTRATIVE_BADGE in text and "targets met - waiting for feedback" in text
    assert "Guitar pickup (6k, 2.5 H)" in text and "Reference models" in text
    assert "Highlighted rows are parameters the agent can change." in [c.value for c in at.caption]
    assert all(b.disabled for b in at.button if b.label in ("Send to Planner", "Accept design"))   # example: read-only
    assert "Read-only: illustrative example." in [c.value for c in at.caption]


def test_real_project_run_has_no_illustrative_badge():
    real = [e for e in data.build_index() if e["set"] is None and not e["illustrative"]]
    if not real:
        pytest.skip("no real project run in runs/")
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.radio[1].set_value(real[0]["run_id"]).run()
    assert not at.exception, at.exception
    assert data.ILLUSTRATIVE_BADGE not in html(at)


def test_benchmark_run_page_renders_without_badge():
    if not [e for e in data.build_index() if e["set"]]:
        pytest.skip("no benchmark runs in runs/bench")
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.radio[0].set_value("Benchmark runs").run()
    assert not at.exception, at.exception
    text = html(at)
    assert data.ILLUSTRATIVE_BADGE not in text and "Benchmark v1" in text


# ---------- live mode (actions stubbed: no worker, no simulation) ----------
def live_app(monkeypatch, tmp_path, status=None):
    from pedal_agent.graph import RunStore, new_run
    from pedal_agent.llm import FakeLLM
    from pedal_agent.schemas import MetricTarget, Step
    runs = tmp_path / "runs"
    monkeypatch.setenv("PEDAL_RUNS_DIR", str(runs))
    monkeypatch.setenv("PEDAL_DASHBOARD_LLM", "fake")
    store = RunStore(runs)
    run = None
    if status:
        run = new_run("warm clean jazz tone", FakeLLM())
        run.spec.targets = [MetricTarget(name="gain_1k_db", lo=10.0, hi=20.0, unit="dB", label="Gain at 1 kHz")]
        run.steps.append(Step(n=1, agent="tone_analyst", action="tone_analyst", title="Target spec drafted", why="warm"))
        run.status = status
        store.save(run)
    calls = []
    for name in ("create_project", "approve_spec", "reject_spec", "send_feedback", "accept"):
        monkeypatch.setattr(actions, name, lambda *a, _n=name, **k: calls.append((_n, a, k)) or "new-run-id")
    return AppTest.from_file(APP, default_timeout=60), store, run, calls



def test_spec_approval_panel_calls_approve(monkeypatch, tmp_path):
    at, store, run, calls = live_app(monkeypatch, tmp_path, "awaiting_spec_approval")
    at.run()
    assert not at.exception, at.exception
    assert any("Approve the target spec" in m.value for m in at.markdown)
    next(b for b in at.button if b.label == "Approve targets").click().run()
    assert calls == [("approve_spec", (run.run_id, None), {"llm": "fake", "store": calls[0][2]["store"]})]


def test_create_form_calls_create_project_and_lock_disables_it(monkeypatch, tmp_path):
    at, store, _, calls = live_app(monkeypatch, tmp_path)
    at.run()
    assert not at.exception, at.exception
    at.text_input[0].input("Jazz Christmas")
    at.text_area[0].input("warm, clean jazz tone")
    next(b for b in at.button if b.label == "Create and draft target spec").click().run()
    assert calls and calls[0][0] == "create_project" and calls[0][1][:3] == ("Jazz Christmas", None, "warm, clean jazz tone")
    (store.dir / actions.LOCK_NAME).write_text('{"run_id": "other", "pid": 0}', encoding="utf-8")   # a starting worker
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert next(b for b in at.button if b.label == "Create and draft target spec").disabled
    assert any("one run at a time" in c.value for c in at.caption)
