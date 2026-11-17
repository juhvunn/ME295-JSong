"""The Streamlit page runs without errors (streamlit.testing, no browser, no simulations)."""
import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from dashboard import data  # noqa: E402
from pedal_agent.config import REPO_ROOT  # noqa: E402

APP = str(REPO_ROOT / "dashboard" / "app.py")


def html(at) -> str:
    return "\n".join(m.value for m in at.markdown)


def test_example_run_page_renders_with_illustrative_badge():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception, at.exception
    text = html(at)
    assert data.ILLUSTRATIVE_BADGE in text and "targets met - waiting for feedback" in text
    assert "Guitar pickup (6k, 2.5 H)" in text and "Reference models" in text
    assert "Highlighted rows are parameters the agent can change." in [c.value for c in at.caption]
    assert all(b.disabled for b in at.button)                      # read-only version


def test_benchmark_run_page_renders_without_badge():
    if not [e for e in data.build_index() if e["set"]]:
        pytest.skip("no benchmark runs in runs/bench")
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.radio[0].set_value("Benchmark runs").run()
    assert not at.exception, at.exception
    text = html(at)
    assert data.ILLUSTRATIVE_BADGE not in text and "Benchmark v1" in text
