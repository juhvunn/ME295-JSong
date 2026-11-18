"""Demo sound (pedal_agent/audio.py): clip loading, the clip-source filter, renders under the one-run lock."""
import hashlib
import json
import os

import numpy as np
import pytest
from scipy.io import wavfile

from pedal_agent import actions, audio
from pedal_agent.checker import build_netlist
from pedal_agent.config import REPO_ROOT
from pedal_agent.graph import RunStore
from pedal_agent.schemas import RunRecord
from pedal_agent.tools.simulate import CLIP_SOURCE, UnsafeNetlistError, check_netlist

EXAMPLE = REPO_ROOT / "runs" / "example-jazz-christmas.json"


def example_run(status="accepted") -> RunRecord:
    run = RunRecord.model_validate_json(EXAMPLE.read_text(encoding="utf-8"))
    run.run_id, run.status = "20261118-audio-test", status
    return run


@pytest.fixture
def clips(tmp_path, monkeypatch):
    d = tmp_path / "audio"
    d.mkdir()
    monkeypatch.setenv("PEDAL_CLIPS_DIR", str(d))
    return d


def tone(path, fs=48000, seconds=1.0, channels=1, amp=0.4):
    t = np.arange(int(fs * seconds)) / fs
    x = (amp * np.sin(2 * np.pi * 110 * t) * 32767).astype(np.int16)
    wavfile.write(path, fs, np.c_[(x,) * channels] if channels > 1 else x)
    return path


# ---------- safety filter ----------
def test_only_the_fixed_clip_source_may_name_a_file():
    check_netlist(CLIP_SOURCE, clip=True)                                   # audio renders: allowed
    with pytest.raises(UnsafeNetlistError):
        check_netlist(CLIP_SOURCE)                                          # Checker sims: never
    bad = ['.model s filesource (file="../../.env")',
           CLIP_SOURCE.replace("clip.txt", "C:/secret.txt"),
           "a1 [x] d_src\n.model d_src d_source (input_file=\"x.txt\")",
           "A_clip %v([emf]) other\n.model other filesource ()"]
    for net in bad:
        for clip in (False, True):
            with pytest.raises(UnsafeNetlistError):
                check_netlist(net, clip=clip)


def test_checker_netlist_unchanged_and_render_netlist_uses_the_clip_source():
    run = example_run()
    net, _ = build_netlist(run.best.candidate, run.spec.test_signal["f0_hz"], run.spec.test_signal["amp_v"])
    assert hashlib.sha256(net.encode()).hexdigest() == run.best.report.netlist_sha256   # Checker: byte-identical
    a = audio.design_netlist(run.best.candidate, 44100, 44100)
    check_netlist(a, clip=True)
    assert CLIP_SOURCE in a and "Vsrc" not in a and "tran 2.267573696e-05 1 0 2.267573696e-05" in a
    circuit = lambda n, src: [l for l in n.split(".control")[0].splitlines() if l not in src]  # noqa: E731
    assert circuit(a, CLIP_SOURCE.splitlines()) == circuit(net, [l for l in net.splitlines() if l.startswith("Vsrc")])
    # same models, blocks, pickup and load as the Checker; only the source and the analyses differ


# ---------- clips ----------
def test_load_clip_scales_to_the_pickup_peak_and_rejects_unusable_files(clips):
    fs, x = audio.load_clip(tone(clips / "a.wav"))
    assert fs == 48000 and len(x) == 48000 and abs(np.abs(x).max() - audio.cfg()["input_peak_v"]) < 1e-12
    assert x[0] == 0 and x[-1] == 0                                         # faded in and out
    long = tone(clips / "long.wav", fs=44100, seconds=audio.cfg()["clip_s"] + 2)
    assert len(audio.load_clip(long)[1]) == audio.cfg()["clip_s"] * 44100     # trimmed to clip_s
    for bad, why in [(tone(clips / "st.wav", channels=2), "mono"), (tone(clips / "r.wav", fs=22050), "44100"),
                     (tone(clips / "s.wav", amp=0), "silent"), (tone(clips / "short.wav", seconds=0.2), "0.5 s")]:
        with pytest.raises(audio.ClipError, match=why):
            audio.load_clip(bad)
    assert [c.name for c in audio.clips()] == ["a.wav", "long.wav", "r.wav", "s.wav", "short.wav", "st.wav",
                                                audio.SYNTH_NAME]


def test_synthetic_clip_is_generated_on_first_use_and_identical_every_time(clips, tmp_path):
    assert not (clips / audio.SYNTH_NAME).exists()
    assert [c.name for c in audio.clips()] == [audio.SYNTH_NAME]           # generated on first use
    fs, x = wavfile.read(clips / audio.SYNTH_NAME)
    assert fs == 44100 and x.dtype == np.int16 and len(x) == 8 * 44100
    assert abs(20 * np.log10(np.abs(x).max() / 32767) + 6) < 0.1          # peak -6 dBFS
    again = audio.synth(tmp_path / "again.wav")
    assert again.read_bytes() == (clips / audio.SYNTH_NAME).read_bytes()   # deterministic


# ---------- render ----------
def test_render_writes_wavs_and_meta_and_is_cached_per_clip_file(clips, tmp_path):
    run = example_run()
    clip = tone(clips / "riff.wav", seconds=0.6)
    (m,) = audio.render_all(tmp_path, run, ["riff.wav"])
    assert "error" not in m and m["oversample"] == 1, m.get("error")
    out = audio.folder(tmp_path, run.run_id, clip)
    for f in ("dry.wav", "processed.wav"):
        fs, y = wavfile.read(out / f)
        assert fs == 48000 and len(y) == int(0.6 * 48000)
        assert abs(20 * np.log10(np.abs(y).max() / 32767) - audio.cfg()["out_dbfs"]) < 0.01
    assert 0.01 < m["output_peak_v"] < 5 and m["step"] == run.best.n and m["input_peak_v"] == 0.3
    assert json.loads((out / "meta.json").read_text(encoding="utf-8")) == m
    assert audio.rendered(tmp_path, run, clip) == m and audio.render_all(tmp_path, run, ["riff.wav"]) == []  # cached
    tone(clip, seconds=0.6, amp=0.3)                                        # re-recorded clip: stale
    assert audio.rendered(tmp_path, run, clip) is None


def test_oversample_2_simulates_at_twice_the_rate_and_returns_the_clip_rate(clips, tmp_path, monkeypatch):
    run = example_run()
    clip = tone(clips / "riff.wav", seconds=0.6)
    base = audio.cfg()
    monkeypatch.setattr(audio, "cfg", lambda: base | {"oversample": 2})
    assert "tran 1.041666667e-05 1 0 1.041666667e-05" in audio.design_netlist(run.best.candidate, 48000, 48000, 2)
    (m,) = audio.render_all(tmp_path, run, ["riff.wav"])
    assert "error" not in m and m["oversample"] == 2, m.get("error")
    fs, y = wavfile.read(audio.folder(tmp_path, run.run_id, clip) / "processed.wav")
    assert fs == 48000 and len(y) == int(0.6 * 48000)
    assert "twice the clip's sample rate" in audio.aliasing_text()
    monkeypatch.setattr(audio, "cfg", lambda: base | {"oversample": 1})
    assert audio.rendered(tmp_path, run, clip) is None and "can fold back" in audio.aliasing_text()  # setting changed
    monkeypatch.setattr(audio, "cfg", lambda: base | {"oversample": 3})
    with pytest.raises(ValueError, match="1 or 2"):
        audio.oversample()


def test_failed_clip_is_recorded_and_retried(clips, tmp_path):
    run = example_run()
    tone(clips / "stereo.wav", channels=2)
    (m,) = audio.render_all(tmp_path, run, ["stereo.wav"])
    assert "mono" in m["error"] and audio.rendered(tmp_path, run, clips / "stereo.wav") == m
    assert len(audio.render_all(tmp_path, run, ["stereo.wav"])) == 1        # a failed render is tried again


# ---------- actions: same lock as agent runs ----------
def test_render_audio_needs_an_accepted_run_a_clip_and_the_free_lock(clips, tmp_path, monkeypatch):
    store = RunStore(tmp_path / "runs")
    run = example_run("awaiting_feedback")
    store.save(run)
    with pytest.raises(actions.WrongState):
        actions.render_audio(run.run_id, store=store)
    run.status = "accepted"
    store.save(run)
    tone(clips / "riff.wav")
    with pytest.raises(ValueError, match="no clip"):
        actions.render_audio(run.run_id, "other.wav", store=store)
    actions._acquire(store, "agent-run", pid=os.getpid())                   # an agent run is simulating
    with pytest.raises(actions.Busy):
        actions.render_audio(run.run_id, store=store)
    actions._release(store, "agent-run")
    started = []
    monkeypatch.setattr(actions, "_start", lambda s, rid, args, task="agent": started.append((rid, args, task)))
    actions.render_audio(run.run_id, "riff.wav", store=store)
    assert started == [(run.run_id, ["audio", run.run_id, "--runs-dir", str(store.dir), "--clip", "riff.wav"], "audio")]


def test_audio_lock_blocks_agent_actions(tmp_path):
    store = RunStore(tmp_path / "runs")
    actions._acquire(store, "accepted-run", pid=os.getpid(), task="audio")
    assert actions.active(store)["task"] == "audio"
    with pytest.raises(actions.Busy):
        actions.create_project("Jazz", "jazz", "warm clean jazz tone", llm="fake", store=store)
    actions._release(store, "accepted-run")


def test_accept_starts_the_render(clips, tmp_path, monkeypatch):
    store = RunStore(tmp_path / "runs")
    run = example_run("awaiting_feedback")
    store.save(run)
    calls = []
    monkeypatch.setattr(actions, "work", lambda s, rid, *a: actions._release(s, rid))
    monkeypatch.setattr(actions, "render_audio", lambda rid, store=None: calls.append(rid))
    actions.accept(run.run_id, store=store)
    assert calls == [run.run_id] and actions.active(store) is None
