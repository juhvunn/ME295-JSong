"""Export of an accepted design (pedal_agent/export.py): exact simulated netlist, BOM, summary, refusals."""
import csv
import hashlib
import re

import pytest

from pedal_agent import actions, export
from pedal_agent.checker import check
from pedal_agent.graph import RunStore, new_run
from pedal_agent.llm import FakeLLM
from pedal_agent.schemas import BlockInstance, Candidate, MetricTarget, Step

CHAIN = [BlockInstance(block_id="od_ts808", params={"drive": 0.8}),
         BlockInstance(block_id="dist_distplus", params={"gain": 0.0, "C4": "68n"})]


@pytest.fixture(scope="module")
def report():
    run = new_run("tight crunch", FakeLLM())
    run.spec.targets = [MetricTarget(name="gain_1k_db", lo=10.0, hi=60.0, unit="dB", label="Gain at 1 kHz")]
    return check(Candidate(chain=CHAIN, rationale="test"), run.spec)


def accepted_run(tmp_path, report, status="accepted"):
    store = RunStore(tmp_path / "runs")
    run = new_run("tight crunch", FakeLLM())
    run.spec.targets = [MetricTarget(name="gain_1k_db", lo=10.0, hi=60.0, unit="dB", label="Gain at 1 kHz")]
    run.steps = [Step(n=1, agent="planner", action="initial_chain", title="t", why="w",
                      candidate=Candidate(chain=CHAIN, rationale="test"), report=report.model_copy(deep=True)),
                 Step(n=2, agent="human", action="human_accept", title="Design accepted", why="")]
    run.best_step, run.sims_used, run.status = 1, 1, status
    store.save(run)
    return store, run


def subckt_designators(net: str, name: str) -> list[str]:
    body = re.search(rf"(?ms)^\.subckt {name} .*?^\.ends", net).group(0)
    return [ln.split()[0] for ln in body.splitlines()[1:-1] if ln[:1] in export.KIND]


def test_export_writes_the_simulated_netlist_bom_and_summary(tmp_path, report):
    store, run = accepted_run(tmp_path, report)
    out = export.export_run(run.run_id, store, project_name="Crunch test")
    assert out == tmp_path / "exports" / run.run_id
    net = (out / "netlist.cir").read_bytes()
    assert hashlib.sha256(net).hexdigest() == report.netlist_sha256          # byte-identical to what was simulated
    rows = list(csv.DictReader((out / "bom.csv").open(encoding="utf-8-sig")))
    for pos, name in ((1, "od_ts808"), (2, "dist_distplus")):
        want = []
        for d in subckt_designators(net.decode(), name):                       # pot halves R20A/R20B -> R20
            d = d[:-1] if re.fullmatch(r"R\d+[AB]", d) else d
            want += [d] if d not in want else []
        assert [r["designator"] for r in rows if r["block_pos"] == str(pos)] == want
    by = {(r["block_id"], r["designator"]): r for r in rows}
    assert by[("od_ts808", "R19")]["setting"].startswith("drive = 0.8") and by[("od_ts808", "R19")]["value"] == "500kΩ"
    assert by[("od_ts808", "C3")]["note"] == "default"
    assert by[("dist_distplus", "C4")]["value"] == "68nF" and by[("dist_distplus", "C4")]["note"] == "agent-set (default 47n)"
    assert by[("dist_distplus", "D1")]["spice_model"] and by[("dist_distplus", "D1")]["setting"] == "D_clip = si"
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "# Exported design: Crunch test" in summary and report.netlist_sha256 in summary
    assert "C4 = 68n" in summary and "C3 = 47n (default)" in summary and "| Gain at 1 kHz |" in summary
    assert "bypass switching" in summary and "not built or listened to" in summary.replace("\n", " ")
    for i, b in enumerate(CHAIN, start=1):                                     # one schematic per block, SVG + PNG
        svg, png = out / f"schematic_{i}_{b.block_id}.svg", out / f"schematic_{i}_{b.block_id}.png"
        assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" and b"<svg" in svg.read_bytes()[:2000]
        assert f"`{svg.name}`" in summary and f"`{png.name}`" in summary
    assert b"<!-- drive 0.80 (1 = max drive) -->" in (out / "schematic_1_od_ts808.svg").read_bytes()   # glyph comment
    with pytest.raises(FileExistsError):                                       # never overwritten
        export.export_run(run.run_id, store)


def test_export_without_a_matching_schematic_still_exports_and_says_so(tmp_path, report, monkeypatch):
    store, run = accepted_run(tmp_path, report)

    def broken(block_id, params):
        raise export.schematics.DrawingMismatch(f"{block_id}: node m1 is drawn as 2 separate nets")
    monkeypatch.setattr(export.schematics, "images", broken)
    out = export.export_run(run.run_id, store)
    assert not list(out.glob("schematic_*")) and (out / "netlist.cir").exists()
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "block 1 `od_ts808`: no schematic (od_ts808: node m1 is drawn as 2 separate nets)" in summary


def test_export_refuses_unaccepted_runs_and_changed_netlists(tmp_path, report):
    store, run = accepted_run(tmp_path, report, status="awaiting_feedback")
    with pytest.raises(export.NotExportable):
        export.export_run(run.run_id, store)
    with pytest.raises(actions.WrongState):
        actions.export_design(run.run_id, store=store)
    run.status = "accepted"
    run.steps[0].report.netlist_sha256 = "0" * 64                              # e.g. a block changed since the run
    store.save(run)
    with pytest.raises(export.NotExportable, match="differs"):
        export.export_run(run.run_id, store)
    assert not (tmp_path / "exports").exists()


def test_eng_notation():
    assert [export.eng(x, "F") for x in (4.7e-08, 1e-9, 2.2e-6, 51e-12)] == ["47nF", "1nF", "2.2uF", "51pF"]
    assert [export.eng(x, "Ω") for x in (1.5e6, 4700, 220, 0)] == ["1.5MegΩ", "4.7kΩ", "220Ω", "0Ω"]
    assert export.same("47n", 4.7e-08) and not export.same("47n", "68n")
