"""Test result charts (dashboard/charts.py): native SVG Vega-Lite charts, sized and scaled to the data."""
from dashboard import charts, data
from pedal_agent.config import REPO_ROOT

PLOTS = data.load_run(REPO_ROOT / "runs" / "example-jazz-christmas.json").best.report.plots


def layers(spec):
    return {l["mark"]["type"] if isinstance(l["mark"], dict) else l["mark"]: l for l in spec["layer"]}


def test_both_charts_are_svg_same_height_with_hover():
    for chart in (charts.waveform_chart(PLOTS), charts.response_chart(PLOTS)):
        spec = chart.to_dict()
        assert spec["usermeta"]["embedOptions"]["renderer"] == "svg"          # vector: sharp at any zoom
        assert spec["height"] == charts.CHART_H and "width" not in spec         # width follows the column
        assert spec["config"]["legend"]["orient"] == "top-left"                # legend inside, at the top
        assert any("tooltip" in l["encoding"] for l in spec["layer"])         # exact values on hover
        assert any(p["select"]["on"] == "pointerover" and p["select"]["nearest"] for p in spec["params"])


def test_waveform_in_volts_uses_mV_and_a_padded_range_around_the_data():
    spec = charts.waveform_chart(PLOTS, normalized=False).to_dict()
    y = layers(spec)["line"]["encoding"]["y"]
    lo, hi = y["scale"]["domain"]
    vals = [v * 1e3 for v in PLOTS.v_in + PLOTS.v_out]                        # |v| < 1 V -> mV
    assert y["title"] == "mV" and lo < min(vals) and hi > max(vals)
    assert hi - max(vals) < 0.4 * (max(vals) - min(vals)) and min(vals) - lo < 0.1 * (max(vals) - min(vals))
    assert "zero" in y["scale"] and y["scale"]["zero"] is False


def test_response_is_log_20Hz_to_20kHz():
    x = layers(charts.response_chart(PLOTS).to_dict())["line"]["encoding"]["x"]
    assert x["scale"]["type"] == "log" and x["scale"]["domain"] == [20, 20000]


def test_waveform_normalized_by_default_with_actual_peaks_in_legend():
    spec = charts.waveform_chart(PLOTS).to_dict()
    line = layers(spec)["line"]
    y, names = line["encoding"]["y"], line["encoding"]["color"]["scale"]["domain"]
    assert y["title"] == "normalized (peak = 1)"
    rows = next(v for v in spec["datasets"].values() if any("signal" in r for r in v))    # the plotted (long) data
    for name in names:
        assert max(abs(r["v"]) for r in rows if r["signal"] == name) == 1.0                # each trace peaks at 1
    pk_in, pk_out = max(map(abs, PLOTS.v_in)), max(map(abs, PLOTS.v_out))
    assert names == [f"Input (peak {charts._peak_text(pk_in)})", f"Output (peak {charts._peak_text(pk_out)})"]
    tips = [t["title"] for l in spec["layer"] for t in l["encoding"].get("tooltip", [])]
    assert "input (mV)" in tips and "output (mV)" in tips                                  # hover: actual values
