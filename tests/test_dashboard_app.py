"""The Streamlit page runs without errors (streamlit.testing, no browser, no simulations)."""
import json

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
    blocks = data.load_run(example["path"]).best.candidate.chain           # one schematic per block, no placeholder
    assert [b.proto.label for b in at.get("download_button")] == ["Download PNG", "Download SVG"] * len(blocks)
    assert [e.label for e in at.expander].count("Full size") == len(blocks) and not at.warning
    assert "Schematic placeholder" not in text


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


def test_accepted_run_offers_export_then_downloads(monkeypatch, tmp_path):
    at, store, _, calls = live_app(monkeypatch, tmp_path)
    example = next(REPO_ROOT.glob("runs/example-jazz-christmas*.json"))
    run = data.load_run(example)
    run.run_id, run.status, run.stop_reason = "20261117-jazz-accepted", "accepted", "human_accept"   # a real project run
    store.save(run)
    monkeypatch.setattr(actions, "export_design", lambda *a, **k: calls.append(("export_design", a, k)))
    at.run()
    assert not at.exception, at.exception
    next(b for b in at.button if b.label == "Export design (netlist, BOM, summary)").click().run()
    assert calls[-1][0] == "export_design" and calls[-1][1] == (run.run_id,)
    folder = actions.export_folder(run.run_id, store)
    folder.mkdir(parents=True)
    for f in ("bom.csv", "netlist.cir", "summary.md"):
        (folder / f).write_text("x", encoding="utf-8")
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception, at.exception
    assert not [b for b in at.button if b.label.startswith("Export design")]
    assert any(f"exported to {folder}" in c.value for c in at.caption)


def test_center_column_order():
    """Header, chain, schematics, demo sound | feedback, test result, design choices, component list (DASHBOARD_SPEC 1)."""
    at = AppTest.from_file(APP, default_timeout=60).run()
    example = next(e for e in data.build_index() if "example-jazz-christmas" in e["path"])
    at.radio[1].set_value(example["run_id"]).run()
    assert not at.exception, at.exception
    order = ["Selected project", "Signal chain", "Block schematic", "Demo sound", "Feedback", "Test result",
             "Design choices", "Component list"]
    texts = [m.value for m in at.markdown]
    first = [next(i for i, t in enumerate(texts) if name in t) for name in order]
    assert first == sorted(first), dict(zip(order, first))
    assert "Highlighted rows are parameters the agent can change." in [c.value for c in at.caption]


def test_waveform_scale_toggle_defaults_to_normalized():
    at = AppTest.from_file(APP, default_timeout=60).run()
    example = next(e for e in data.build_index() if "example-jazz-christmas" in e["path"])
    at.radio[1].set_value(example["run_id"]).run()
    toggle = at.button_group(key="wave_scale")
    assert toggle.value == "Normalized"

    def wave_y_title():
        chart = next(c for c in at.get("vega_lite_chart") if '"Waveform"' in c.proto.spec)
        return json.loads(chart.proto.spec)["layer"][0]["encoding"]["y"]["title"]

    assert wave_y_title() == "normalized (peak = 1)"
    toggle.set_value("Volts").run()
    assert not at.exception, at.exception
    assert wave_y_title() in ("mV", "V")


# ---------- demo sound (Phase 6) ----------
def accepted_with_clip(monkeypatch, tmp_path):
    import numpy as np
    from scipy.io import wavfile
    from pedal_agent import audio
    clips = tmp_path / "audio"
    clips.mkdir()
    monkeypatch.setenv("PEDAL_CLIPS_DIR", str(clips))
    wavfile.write(clips / "di_riff.wav", 48000, (np.sin(np.arange(48000) / 20) * 9000).astype(np.int16))
    at, store, _, calls = live_app(monkeypatch, tmp_path)
    monkeypatch.setattr(actions, "render_audio", lambda *a, **k: calls.append(("render_audio", a, k)))
    run = data.load_run(next(REPO_ROOT.glob("runs/example-jazz-christmas*.json")))
    run.run_id, run.status = "20261118-jazz-accepted", "accepted"
    store.save(run)
    return at, store, run, calls, audio, clips / "di_riff.wav"


def test_demo_sound_offers_render_then_plays_with_level_and_assumption(monkeypatch, tmp_path):
    at, store, run, calls, audio, clip = accepted_with_clip(monkeypatch, tmp_path)
    at.run()
    assert not at.exception, at.exception
    assert at.selectbox(key="clip").options == ["di riff", "synthetic plucks"]
    next(b for b in at.button if b.label == "Render demo sound").click().run()
    assert calls[-1][0] == "render_audio" and calls[-1][1] == (run.run_id, "di_riff.wav")
    out = audio.folder(store.dir, run.run_id, clip)                       # what the worker would have written
    out.mkdir(parents=True)
    for f in ("dry.wav", "processed.wav"):
        (out / f).write_bytes(clip.read_bytes())
    meta = audio._key(run, clip) | {"input_peak_v": 0.3, "out_dbfs": -1.0, "oversample": 1, "fs": 48000, "seconds": 1.0,
                                    "output_peak_v": 0.217}
    (out / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception, at.exception
    assert len(at.get("audio")) == 1 and not [b for b in at.button if b.label == "Render demo sound"]
    captions = " ".join(c.value for c in at.caption)
    assert "output peak 0.217 V (-13.3 dBV)" in captions and "0.3 V peak EMF at the pickup" in captions
    assert "about 1 V" in captions


def test_demo_sound_waits_for_acceptance(monkeypatch, tmp_path):
    at, store, run, calls, audio, clip = accepted_with_clip(monkeypatch, tmp_path)
    run.status = "awaiting_feedback"
    store.save(run)
    at.run()
    assert not at.exception, at.exception
    assert "The demo sound is rendered when the design is accepted." in [c.value for c in at.caption]
    assert not at.get("audio") and not [b for b in at.button if "demo sound" in b.label]
