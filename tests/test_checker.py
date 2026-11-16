"""pytest: Checker contract (runs ngspice with placeholder models)."""
from pathlib import Path
from pedal_agent.schemas import TargetSpec, MetricTarget, Candidate, BlockInstance, RunRecord
from pedal_agent.checker import check

SPEC = TargetSpec(goal_text="test", targets=[
    MetricTarget(name="ac_peak_hz", lo=500, hi=1200, label="Mid peak"),
    MetricTarget(name="thd_pct", hi=1000, label="THD")])

def test_ts808_default_passes_dc_and_mid_hump():
    rep = check(Candidate(chain=[BlockInstance(block_id="od_ts808")], rationale=""), SPEC)
    assert rep.dc_ok and not rep.errors
    assert rep.results[0].status == "pass"          # mid hump in 500-1200 Hz
    assert rep.netlist_sha256 and rep.plots and len(rep.plots.v_out) > 10

def test_more_drive_more_distortion():
    lo = check(Candidate(chain=[BlockInstance(block_id="od_ts808", params={"drive": 0.1})], rationale=""), SPEC)
    hi = check(Candidate(chain=[BlockInstance(block_id="od_ts808", params={"drive": 0.9})], rationale=""), SPEC)
    assert hi.metrics["thd_pct"] > lo.metrics["thd_pct"]

def test_fuzz_is_asymmetric_distortion_plus_is_symmetric():
    fz = check(Candidate(chain=[BlockInstance(block_id="fuzz_ff_si")], rationale=""), SPEC)
    dp = check(Candidate(chain=[BlockInstance(block_id="dist_distplus")], rationale=""), SPEC)
    assert fz.metrics["even_odd"] > 0.3 > dp.metrics["even_odd"]

def test_example_run_record_roundtrip():
    p = Path(__file__).resolve().parents[1] / "runs" / "example-jazz-christmas.json"
    if p.exists():
        RunRecord.model_validate_json(p.read_text(encoding="utf-8"))
