"""Test result charts for the dashboard (Altair / Vega-Lite, drawn by the page as SVG, not images).

Both charts: same height and margins, legend at the top inside the plot (with headroom above the data), y range with
padding, hover guide line with exact values in a tooltip, width set by the page column.
"""
import altair as alt
import pandas as pd

BLUE, ORANGE = "#2a78d6", "#eb6834"                 # same as dashboard/app.py
CHART_H = 400                                    # px, whole chart (plot area about 290 px) for both Test result charts
Y_AXIS_W = 52                                    # px reserved for y tick labels, so both plots line up
EMBED = {"embedOptions": {"renderer": "svg", "actions": False}}   # vector output: sharp at any zoom


def _style(chart: alt.Chart) -> alt.Chart:
    """Same height, margins, fonts and legend placement for both charts."""
    return (chart.properties(height=CHART_H, usermeta=EMBED)
            .configure_axis(labelFontSize=11, titleFontSize=12, grid=True, gridColor="#ecebe6")
            .configure_axisY(minExtent=Y_AXIS_W)
            .configure_axisX(labelOverlap="greedy")
            .configure_legend(orient="top-left", direction="horizontal", fillColor="#ffffffdd", padding=4,
                              labelFontSize=11, title=None, symbolType="stroke", symbolStrokeWidth=2.5,
                              symbolSize=300)
            .configure_title(fontSize=13, anchor="start", subtitleFontSize=11, subtitleColor="#6b6a64")
            .configure_view(stroke="#d6d5cf"))


def _domain(lo: float, hi: float) -> list[float]:
    """y range with a little padding below and headroom above for the legend inside the plot."""
    span = hi - lo or 1.0
    return [lo - 0.08 * span, hi + 0.30 * span]


def _hover(field: str):
    return alt.selection_point(nearest=True, on="pointerover", fields=[field], empty=False, clear="pointerout")


def waveform_chart(p) -> alt.Chart:
    """Input (dashed blue) and output (orange) over the last two periods; mV when both stay below 1 V."""
    big = max(map(abs, p.v_in + p.v_out)) >= 1.0
    k, unit = (1.0, "V") if big else (1e3, "mV")
    t = [x * 1e3 for x in p.t_s]
    wide = pd.DataFrame({"t": t, "Input": [v * k for v in p.v_in], "Output": [v * k for v in p.v_out]})
    lo, hi = min(wide[["Input", "Output"]].min()), max(wide[["Input", "Output"]].max())
    long = wide.melt("t", var_name="signal", value_name="v")
    sig = alt.Scale(domain=["Input", "Output"], range=[BLUE, ORANGE])
    x = alt.X("t:Q", title="time (ms)", scale=alt.Scale(nice=False, zero=False), axis=alt.Axis(tickCount=6))
    lines = alt.Chart(long).mark_line(strokeWidth=2).encode(
        x=x, y=alt.Y("v:Q", title=unit, scale=alt.Scale(domain=_domain(lo, hi), nice=False, zero=False),
                     axis=alt.Axis(tickCount=6)),
        color=alt.Color("signal:N", scale=sig, legend=alt.Legend()),
        strokeDash=alt.StrokeDash("signal:N", scale=alt.Scale(domain=["Input", "Output"], range=[[6, 4], [1, 0]]),
                                  legend=alt.Legend()))          # same field: merged with the colour legend
    hover = _hover("t")
    rule = alt.Chart(wide).mark_rule(color="#8a8982").encode(
        x="t:Q", opacity=alt.condition(hover, alt.value(0.6), alt.value(0)),
        tooltip=[alt.Tooltip("t:Q", title="time (ms)", format=".3f"),
                 alt.Tooltip("Input:Q", title=f"input ({unit})", format=".1f" if unit == "mV" else ".3f"),
                 alt.Tooltip("Output:Q", title=f"output ({unit})", format=".1f" if unit == "mV" else ".3f")]
    ).add_params(hover)
    dots = lines.mark_point(filled=True, size=40).encode(
        opacity=alt.condition(hover, alt.value(1), alt.value(0))).transform_filter(hover)
    return _style(alt.layer(lines, rule, dots).properties(title=alt.TitleParams("Waveform", subtitle="last 2 periods")))


def response_chart(p) -> alt.Chart:
    """Gain in dB of the whole chain (pickup EMF to output), 20 Hz - 20 kHz on a log axis."""
    fr = pd.DataFrame({"Hz": p.freq_hz, "dB": p.mag_db, "signal": "Output gain"})
    fr = fr[(fr.Hz >= 20) & (fr.Hz <= 20000)]
    lo, hi = fr.dB.min(), fr.dB.max()
    x = alt.X("Hz:Q", title="frequency (Hz)", scale=alt.Scale(type="log", domain=[20, 20000], nice=False),
              axis=alt.Axis(values=[20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000], format="~s"))
    line = alt.Chart(fr).mark_line(strokeWidth=2).encode(
        x=x, y=alt.Y("dB:Q", title="dB", scale=alt.Scale(domain=_domain(lo, hi), nice=False, zero=False),
                     axis=alt.Axis(tickCount=6)),
        color=alt.Color("signal:N", scale=alt.Scale(domain=["Output gain"], range=[ORANGE]), legend=alt.Legend()))
    hover = _hover("Hz")
    pts = line.mark_point(filled=True, size=40).encode(
        opacity=alt.condition(hover, alt.value(1), alt.value(0)),
        tooltip=[alt.Tooltip("Hz:Q", title="frequency (Hz)", format=",.0f"),
                 alt.Tooltip("dB:Q", title="gain (dB)", format=".2f")]).add_params(hover)
    rule = alt.Chart(fr).mark_rule(color="#8a8982").encode(
        x="Hz:Q", opacity=alt.condition(hover, alt.value(0.6), alt.value(0))).transform_filter(hover)
    return _style(alt.layer(line, pts, rule).properties(title=alt.TitleParams("Frequency response", subtitle="pickup EMF to output")))
