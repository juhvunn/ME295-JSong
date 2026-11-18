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


def test_waveform_uses_mV_and_a_padded_range_around_the_data():
    spec = charts.waveform_chart(PLOTS).to_dict()
    y = layers(spec)["line"]["encoding"]["y"]
    lo, hi = y["scale"]["domain"]
    vals = [v * 1e3 for v in PLOTS.v_in + PLOTS.v_out]                        # |v| < 1 V -> mV
    assert y["title"] == "mV" and lo < min(vals) and hi > max(vals)
    assert hi - max(vals) < 0.4 * (max(vals) - min(vals)) and min(vals) - lo < 0.1 * (max(vals) - min(vals))
    assert "zero" in y["scale"] and y["scale"]["zero"] is False


def test_response_is_log_20Hz_to_20kHz():
    x = layers(charts.response_chart(PLOTS).to_dict())["line"]["encoding"]["x"]
    assert x["scale"]["type"] == "log" and x["scale"]["domain"] == [20, 20000]
