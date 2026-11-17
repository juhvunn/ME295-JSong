"""Model-file provenance in CheckReport / RunRecord."""
import hashlib
import io
import json

import pytest

import pedal_agent.checker as checker
from pedal_agent.config import REPO_ROOT
from pedal_agent.provenance import describe, flagged, text_sha256, unvalidated_choices
from pedal_agent.schemas import BlockInstance, Candidate, ModelFile, RunRecord, TargetSpec

SPEC = TargetSpec(goal_text="t", targets=[])


def cand(block, **params):
    return Candidate(chain=[BlockInstance(block_id=block, params=params)], rationale="")


def test_sha256_ignores_line_endings(tmp_path):
    lf, crlf = tmp_path / "a.lib", tmp_path / "b.lib"
    lf.write_bytes(b"* x\n.model D1 D(Is=1e-14)\n")
    crlf.write_bytes(b"* x\r\n.model D1 D(Is=1e-14)\r\n")
    assert text_sha256(lf) == text_sha256(crlf) == hashlib.sha256(lf.read_bytes()).hexdigest()


def test_manifest_status():
    models = REPO_ROOT / "models"
    assert describe(models / "smoke_models.lib").status == "placeholder"
    assert describe(models / "opamps.lib").status == "validated"
    assert describe(models / "diodes_fitted.lib").status == "validated"
    assert describe(models / "smoke_models.lib").path == "models/smoke_models.lib"


def test_unvalidated_choices_and_flag():
    assert unvalidated_choices(cand("dist_distplus", D_clip="ge")) == ["dist_distplus.D_clip=ge"]
    assert unvalidated_choices(cand("dist_distplus")) == []          # default si is validated
    ok = ModelFile(path="models/opamps.lib", sha256="x", status="validated")
    ph = ModelFile(path="models/smoke_models.lib", sha256="y", status="placeholder")
    assert flagged([ok], []) is False
    assert flagged([ok, ph], []) is True
    assert flagged([ok], ["dist_distplus.D_clip=ge"]) is True


REAL = ["models/opamps.lib", "models/diodes_fitted.lib", "models/bjts_fitted.lib"]


def test_check_report_records_model_files():
    rep = checker.check(cand("od_ts808"), SPEC)                 # default set: real (config.yaml)
    assert [f.path for f in rep.model_files] == REAL
    assert [f.sha256 for f in rep.model_files] == [text_sha256(REPO_ROOT / p) for p in REAL]
    assert {f.status for f in rep.model_files} == {"validated"}
    assert rep.placeholder_or_unvalidated is False and rep.unvalidated_choices == []


def test_smoke_set_is_flagged(monkeypatch):
    monkeypatch.setattr(checker, "MODEL_SET", "smoke")
    rep = checker.check(cand("od_ts808"), SPEC)
    assert [(f.path, f.status) for f in rep.model_files] == [("models/smoke_models.lib", "placeholder")]
    assert rep.placeholder_or_unvalidated is True


def test_unvalidated_choice_adds_placeholder_file_and_flag():
    rep = checker.check(cand("dist_distplus", D_clip="ge"), SPEC)
    assert [f.path for f in rep.model_files] == REAL + ["models/unvalidated.lib"]
    assert rep.model_files[-1].status == "placeholder"
    assert rep.unvalidated_choices == ["dist_distplus.D_clip=ge"] and rep.placeholder_or_unvalidated is True


def test_unregistered_file_is_flagged_and_hash_follows_content(tmp_path, monkeypatch):
    lib = tmp_path / "copy.lib"
    lib.write_text((REPO_ROOT / "models" / "smoke_models.lib").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(checker, "MODELS", str(lib))
    a = checker.check(cand("od_ts808"), SPEC)
    lib.write_text(lib.read_text(encoding="utf-8") + "\n* edited\n", encoding="utf-8")
    b = checker.check(cand("od_ts808"), SPEC)
    assert a.model_files[0].status == "unregistered" and a.placeholder_or_unvalidated
    assert a.model_files[0].sha256 != b.model_files[0].sha256


def test_run_record_json_carries_flag_and_files(tmp_path):
    from pedal_agent.cli import main
    main(["run", "--goal", "warm overdrive", "--auto-approve", "--no-feedback", "--llm", "fake",
          "--runs-dir", str(tmp_path)], out=(out := io.StringIO()))
    path = next(tmp_path.glob("*.json"))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["placeholder_or_unvalidated"] is False
    assert [f["path"] for f in data["model_files"]] == REAL
    assert "WARNING: placeholder" not in out.getvalue()
    run = RunRecord.model_validate_json(path.read_text(encoding="utf-8"))   # computed fields round-trip
    assert run.placeholder_or_unvalidated is False


def test_old_records_without_provenance_still_load():
    # an "old" record: the example run with the provenance fields removed (as written before they existed)
    d = json.loads((REPO_ROOT / "runs" / "example-jazz-christmas.json").read_text(encoding="utf-8"))
    for key in ("placeholder_or_unvalidated", "model_files"):
        d.pop(key, None)
    for s in d["steps"]:
        for key in ("model_files", "unvalidated_choices", "placeholder_or_unvalidated"):
            (s.get("report") or {}).pop(key, None)
    run = RunRecord.model_validate(d)
    assert run.placeholder_or_unvalidated is None and run.model_files == []


def test_example_run_uses_the_real_model_set():
    run = RunRecord.model_validate_json((REPO_ROOT / "runs" / "example-jazz-christmas.json").read_text(encoding="utf-8"))
    assert run.placeholder_or_unvalidated is False
    assert [f.path for f in run.model_files] == ["models/opamps.lib", "models/diodes_fitted.lib", "models/bjts_fitted.lib"]
