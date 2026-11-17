"""Guitar Pedal Agent dashboard (Phase 5, read-only first version; docs/DASHBOARD_SPEC.md).

Run from the repo root:  streamlit run dashboard/app.py
Reads runs/*.json and runs/bench/** (RunRecords) and the block library through dashboard/data.py; it never
simulates and never writes run files. Block schematic, demo sound and feedback are placeholders.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import altair as alt  # noqa: E402  (bundled with Streamlit)
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard import data  # noqa: E402
from pedal_agent.config import REPO_ROOT, load_config  # noqa: E402

BLUE, ORANGE, ORANGE_LIGHT = "#2a78d6", "#eb6834", "#fde9df"
GENRES = ("Rock", "Pop", "R&B", "Jazz", "Blues", "Metal")
STATUS_ICON = {"Pass": "✓", "Too high": "▲", "Too low": "▼", "Not measured": "–"}
CATEGORY_TITLE = {"overdrive": "Overdrive", "distortion": "Distortion", "fuzz": "Fuzz"}

st.set_page_config(page_title="Guitar Pedal Agent", layout="wide")
st.markdown(f"""<style>
.stApp {{ background: #f6f6f4; }}
.card {{ background: #fff; border: 1px solid #e3e2dc; border-radius: 10px; padding: 14px 16px; margin-bottom: 12px; }}
.card h4 {{ margin: 0 0 8px 0; font-size: 0.95rem; color: #3a3a37; }}
.muted {{ color: #6b6a64; font-size: 0.85rem; }}
.pill {{ display: inline-block; border: 1px solid #d6d5cf; border-radius: 999px; padding: 2px 10px;
        font-size: 0.78rem; margin-left: 6px; background: #fff; color: #3a3a37; }}
.badge {{ display: inline-block; border-radius: 6px; padding: 3px 10px; font-size: 0.82rem;
         background: #f1f0eb; border: 1px solid #d6d5cf; color: #2b2b28; }}
.badge-warn {{ background: #fff4d6; border-color: #e7c86b; }}
.badge-ill {{ background: {ORANGE_LIGHT}; border-color: {ORANGE}; font-weight: 600; }}
.chain {{ display: flex; flex-wrap: wrap; align-items: stretch; gap: 8px; }}
.node {{ border: 1px solid #d6d5cf; border-radius: 8px; padding: 8px 10px; background: #fafaf8; font-size: 0.82rem; }}
.node.block {{ border: 2px solid {ORANGE}; background: #fff; }}
.arrow {{ align-self: center; color: #8a8982; }}
.knob {{ display: inline-block; margin-right: 8px; }}
.knob.changed b {{ color: {ORANGE}; }}
.step {{ border-left: 2px solid #d6d5cf; padding: 4px 0 8px 12px; margin-left: 8px; }}
.tag {{ display: inline-block; font-size: 0.72rem; border: 1px solid #d6d5cf; border-radius: 4px;
       padding: 0 6px; margin-left: 6px; color: #3a3a37; background: #fafaf8; }}
.status {{ display: inline-block; border-radius: 999px; padding: 1px 10px; font-size: 0.8rem; border: 1px solid #d6d5cf; }}
.status.pass {{ background: #e6f4ea; }} .status.fail {{ background: #fdecea; }}
.ref {{ border: 1px solid #e3e2dc; border-radius: 8px; padding: 8px 10px; margin-bottom: 8px; background: #fff; }}
</style>""", unsafe_allow_html=True)


@st.cache_data(ttl=30, show_spinner="Indexing runs…")
def index() -> list[dict]:
    return data.build_index(cache=REPO_ROOT / "results" / "dashboard_index.json")


@st.cache_data(show_spinner=False)
def ngspice() -> str:
    return data.ngspice_version()


@st.cache_data(show_spinner=False)
def library() -> dict:
    return data.library()


def card(title: str, body: str = "") -> None:
    st.markdown(f'<div class="card"><h4>{title}</h4>{body}</div>', unsafe_allow_html=True)


def esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------- title ----------
cfg = load_config()
t1, t2 = st.columns([3, 2])
t1.markdown("## Guitar Pedal Agent\n<span class='muted'>Multi-agent analog pedal design with ngspice</span>",
            unsafe_allow_html=True)
t2.markdown(f"<div style='text-align:right; padding-top:18px'><span class='pill'>{esc(cfg['llm']['model_id'])}</span>"
            f"<span class='pill'>{esc(ngspice())}</span><span class='pill'>read-only</span></div>",
            unsafe_allow_html=True)

left, center, right = st.columns([1, 2.4, 1], gap="medium")

# ---------- LEFT: create project (disabled) + saved circuits ----------
with left:
    with st.container(border=True):
        st.markdown("**Create new project**")
        st.text_input("Project name", disabled=True, placeholder="e.g. Jazz Christmas")
        st.pills("Genre", GENRES, disabled=True)
        st.text_area("Describe the sound", disabled=True, placeholder="Warm, mid-forward lead…", height=80)
        st.text_input("Reference (song or artist)", disabled=True)
        st.button("Create and draft target spec", disabled=True, width="stretch",
                  help="Live runs come in the next dashboard version (DASHBOARD_SPEC section 3).")

    with st.container(border=True):
        st.markdown("**Saved circuits**")
        idx = index()
        source = st.radio("Show", ["Examples", "Benchmark runs"], horizontal=True, label_visibility="collapsed")
        rows = [e for e in idx if (e["set"] is None) == (source == "Examples")]
        if source == "Benchmark runs" and rows:
            f1, f2 = st.columns(2)
            mode = f1.selectbox("Method", sorted({e["mode"] for e in rows}))
            rows = [e for e in rows if e["mode"] == mode]
            target = f2.selectbox("Target", sorted({e["target_id"] for e in rows}))
            rows = [e for e in rows if e["target_id"] == target]
            rows.sort(key=lambda e: e["seed"] or 0)
        if not rows:
            st.caption("No runs found.")
            st.stop()
        label = (lambda e: f"seed {e['seed']} · {e['chain']} · {e['n_pass']}/{e['n_targets']}") \
            if source == "Benchmark runs" else (lambda e: f"{e['name']} · {e['chain']} · {e['n_pass']}/{e['n_targets']}")
        chosen = st.radio("Run", rows, format_func=label, label_visibility="collapsed")
        st.caption(f"{len(idx)} runs indexed")

entry = chosen
run = data.load_run(entry["path"])
steps = data.simulated_steps(run)

# ---------- CENTER ----------
with center:
    default = data.display_step(run)
    if not steps:
        st.info("This run has no simulated step yet.")
        st.stop()
    labels = {s.n: f"Step {s.n}: {s.title}" + (" (best)" if s.n == run.best_step else "") for s in steps}
    shown_n = st.selectbox("Shown step", list(labels), index=list(labels).index(default.n),
                           format_func=labels.get, label_visibility="collapsed")
    step = data.display_step(run, shown_n)
    h = data.header(run, step)

    badges = f"<span class='badge'>{esc(h['badge'])}</span>"
    if h["illustrative"]:
        badges += f" <span class='badge badge-ill'>⚑ {data.ILLUSTRATIVE_BADGE}</span>"
    if h["flagged"]:
        badges += " <span class='badge badge-warn'>⚠ Placeholder or unvalidated models: not for reported results</span>"
    chain = "".join(
        f"<span class='arrow'>→</span><div class='node block'><b>{esc(c['name'])}</b><br>"
        + "".join(f"<span class='knob{' changed' if s['changed'] else ''}'>{esc(s['name'])} <b>{esc(s['value'])}</b></span>"
                  for s in c["settings"]) + "</div>" for c in data.chain_cards(step))
    card("Selected project",
         f"<div style='font-size:1.4rem; font-weight:600'>{esc(h['name'])}</div>"
         f"<div class='muted' style='margin:4px 0 10px'>{esc(h['goal'])}</div>{badges}"
         f"<h4 style='margin-top:14px'>Signal chain</h4>"
         f"<div class='chain'><div class='node'>{esc(data.pickup_text())}</div>{chain}"
         f"<span class='arrow'>→</span><div class='node'>{esc(data.amp_text())}</div></div>"
         f"<div class='muted' style='margin-top:6px'>Highlighted knob values were set by the agent; others are block defaults.</div>")

    for b in step.candidate.chain:
        with st.container(border=True):
            st.markdown(f"**Block schematic** · `{b.block_id}`")
            st.markdown("<div class='muted' style='border:1px dashed #d6d5cf; border-radius:8px; padding:24px; "
                        "text-align:center'>Schematic placeholder (Phase 4: blocks/&lt;id&gt;/schematic.py)</div>",
                        unsafe_allow_html=True)
            st.markdown("**Component list**")
            comps = pd.DataFrame(data.components(b.block_id, b.params))
            styled = comps[["designator", "kind", "value", "parameter", "note"]].style.apply(
                lambda r: [f"background-color: {ORANGE_LIGHT}" if comps.loc[r.name, "adjustable"] else ""] * len(r), axis=1)
            st.dataframe(styled, hide_index=True, width="stretch", height=35 * (len(comps) + 1) + 3)   # all rows
            st.caption("Highlighted rows are parameters the agent can change.")

    with st.container(border=True):
        st.markdown("**Design choices**")
        html = ""
        for c in data.design_choices(run):
            res = f" · {c['n_pass']}/{h['n_targets']} targets" if c["simulated"] else ""
            errs = f"<div class='muted'>Rejected: {esc('; '.join(c['errors']))}</div>" if c["errors"] else ""
            tags = [c["action"]] + ([c["tag"]] if c["tag"] != c["action"] else [])
            html += (f"<div class='step'><b>{c['n']}. {esc(c['title'])}</b>"
                     + "".join(f"<span class='tag'>{esc(t)}</span>" for t in tags) + f"<span class='muted'>{res}</span>"
                     f"<div class='muted'>{esc(c['why'])}</div>{errs}</div>")
        st.markdown(html, unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown(f"**Test result** · step {step.n}")
        p = step.report.plots
        g1, g2 = st.columns(2)
        if p:
            wave = pd.DataFrame({"t (ms)": [t * 1e3 for t in p.t_s] * 2, "V": p.v_in + p.v_out,
                                 "signal": ["Input"] * len(p.t_s) + ["Output"] * len(p.t_s)})
            g1.altair_chart(alt.Chart(wave, title="Waveform (last 2 periods)").mark_line(strokeWidth=2).encode(
                x="t (ms):Q", y=alt.Y("V:Q", title="V", axis=alt.Axis(tickCount=5)),
                color=alt.Color("signal:N", scale=alt.Scale(domain=["Input", "Output"], range=[BLUE, ORANGE]),
                                legend=alt.Legend(orient="bottom", title=None)),
                strokeDash=alt.StrokeDash("signal:N", scale=alt.Scale(domain=["Input", "Output"], range=[[5, 4], [1, 0]]),
                                          legend=None),
                tooltip=["signal", alt.Tooltip("t (ms):Q", format=".3f"), alt.Tooltip("V:Q", format=".3f")]
            ).properties(height=220), width="stretch")
            fr = pd.DataFrame({"Hz": p.freq_hz, "dB": p.mag_db})
            g2.altair_chart(alt.Chart(fr, title="Frequency response").mark_line(strokeWidth=2, color=ORANGE).encode(
                x=alt.X("Hz:Q", scale=alt.Scale(type="log", domain=[20, 20000], nice=False),
                        axis=alt.Axis(values=[20, 100, 1000, 10000, 20000], format="~s")),
                y=alt.Y("dB:Q", axis=alt.Axis(tickCount=5)),
                tooltip=[alt.Tooltip("Hz:Q", format=".0f"), alt.Tooltip("dB:Q", format=".1f")]
            ).properties(height=220), width="stretch")
        else:
            st.caption("No plot data stored for this step.")
        if step.report.errors:
            st.warning("Checker: " + "; ".join(step.report.errors))
        trs = "".join(
            f"<tr><td>{esc(r['target'])}</td><td>{esc(r['range'])}</td><td>{esc(r['measured'])}</td>"
            f"<td><span class='status {'pass' if r['status'] == 'Pass' else 'fail'}'>{STATUS_ICON[r['status']]} "
            f"{esc(r['status'])}</span></td></tr>" for r in data.target_rows(run, step))
        st.markdown("<table style='width:100%; font-size:0.88rem'><tr><th align='left'>Target</th><th align='left'>Range</th>"
                    f"<th align='left'>Measured</th><th align='left'>Status</th></tr>{trs}</table>", unsafe_allow_html=True)

    d1, d2 = st.columns(2)
    with d1.container(border=True):
        st.markdown("**Demo sound**")
        st.selectbox("Clip", ["DI clip (Phase 6)"], disabled=True)
        st.segmented_control("Signal", ["Dry", "Processed"], disabled=True)
        st.button("▶ Play", disabled=True, help="Audio rendering comes in Phase 6.")
    with d2.container(border=True):
        st.markdown("**Feedback**")
        st.text_area("Tell the Planner what to change", disabled=True, height=80)
        b1, b2 = st.columns(2)
        b1.button("Send to Planner", disabled=True, width="stretch")
        b2.button("Accept design", disabled=True, width="stretch")
        st.caption("Feedback and accept act on live runs (next version).")

# ---------- RIGHT ----------
with right:
    with st.container(border=True):
        st.markdown("**Reference models**")
        for cat, blocks in library().items():
            st.markdown(f"<div class='muted' style='margin-top:6px'><b>{CATEGORY_TITLE.get(cat, cat.title())}</b></div>",
                        unsafe_allow_html=True)
            for b in blocks:
                src = f"<a href='{esc(b['url'])}' target='_blank'>{esc(b['source'])}</a>" if b["url"] else esc(b["source"])
                st.markdown(f"<div class='ref'><b>{esc(b['name'])}</b><br><code>{esc(b['block_id'])}</code>"
                            f"<div class='muted'>{esc(b['character'])}</div><div class='muted'>Source: {src}</div></div>",
                            unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown("**Agent run**")
        a = data.agent_panel(run)
        st.markdown(
            f"<table style='width:100%; font-size:0.86rem'>"
            f"<tr><td>Iterations</td><td align='right'>{a['iterations']}</td></tr>"
            f"<tr><td>Simulations</td><td align='right'>{a['sims']}</td></tr>"
            f"<tr><td>Topology changes</td><td align='right'>{a['topology_changes']}</td></tr>"
            f"<tr><td>Stop reason</td><td align='right'>{esc(a['stop_reason'])}</td></tr>"
            f"<tr><td>Mode</td><td align='right'>{esc(a['mode'])}</td></tr>"
            f"<tr><td>Model</td><td align='right'>{esc(a['model'])}</td></tr>"
            f"<tr><td>Tokens</td><td align='right'>{esc(a['tokens'])}</td></tr>"
            f"<tr><td>Cost</td><td align='right'>{esc(a['cost'])}</td></tr>"
            + (f"<tr><td>Benchmark</td><td align='right'>{esc(a['benchmark']['set'])} {esc(a['benchmark']['target'])} "
               f"(cat. {esc(a['benchmark']['category'])}), seed {a['seed']}</td></tr>" if a["benchmark"] else "")
            + "</table>", unsafe_allow_html=True)
        st.markdown("**Repeated runs (same goal)**")
        rep = data.repeated_runs(index(), entry)
        if rep:
            med = rep["median_sims_to_success"]
            st.markdown(f"<div class='muted'>{rep['successes']} of {rep['runs']} runs succeeded "
                        f"({100 * rep['success_rate']:.0f} %)<br>median simulations to success: "
                        f"{'–' if med is None else f'{med:g}'}<br>median simulations used: {rep['median_sims_used']:g}</div>",
                        unsafe_allow_html=True)
        else:
            st.caption("Only one run with this goal and mode.")
