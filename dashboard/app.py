"""Guitar Pedal Agent dashboard (Phase 5; docs/DASHBOARD_SPEC.md).

Run from the repo root:  streamlit run dashboard/app.py
Reads runs/*.json and runs/bench/** (RunRecords) and the block library through dashboard/data.py, and calls
only the backend actions in pedal_agent/actions.py (create project, approve/reject targets, feedback, accept).
The agent runs in a worker process; while it works, the page re-reads the run file every 2 s.
One active run at a time (actions lock). Illustrative examples and benchmark runs are read-only.
LLM: real by default; PEDAL_DASHBOARD_LLM=fake for a demo without API use; PEDAL_RUNS_DIR for another
runs folder. Block schematics come from pedal_agent/schematics (Phase 4); the demo sound is a placeholder (Phase 6).
"""
import base64
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard import data  # noqa: E402
from dashboard.charts import response_chart, waveform_chart  # noqa: E402
from pedal_agent import actions, schematics  # noqa: E402
from pedal_agent.config import REPO_ROOT, load_config  # noqa: E402

BLUE, ORANGE, ORANGE_LIGHT = "#2a78d6", "#eb6834", "#fde9df"
GENRES = ("Rock", "Pop", "R&B", "Jazz", "Blues", "Metal")
LLM = os.environ.get("PEDAL_DASHBOARD_LLM", "real")
RUNS_DIR = os.environ.get("PEDAL_RUNS_DIR")             # default: runs/ from config.yaml
REFRESH_S = 2
SCROLL_HEIGHT = 400                       # px; design choices and component lists scroll inside boxes this tall
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
def index(runs_dir: str | None = None) -> list[dict]:
    if runs_dir:                                             # tests / a separate runs folder: no shared cache
        return data.build_index(Path(runs_dir))
    return data.build_index(cache=REPO_ROOT / "results" / "dashboard_index.json")


@st.cache_data(show_spinner=False)
def ngspice() -> str:
    return data.ngspice_version()


@st.cache_data(show_spinner=False)
def library() -> dict:
    return data.library()


@st.cache_data(show_spinner="Drawing schematic…", max_entries=64)
def schematic(block_id: str, params_json: str) -> dict:
    """PNG/SVG of a block at these settings (pedal_agent/schematics; connections checked against the netlist)."""
    return schematics.images(block_id, json.loads(params_json))


def show_schematic(pos: int, block_id: str, params: dict, n: int) -> None:
    """Fitted to the column; full size in an expander (scrolls sideways) and as PNG/SVG downloads."""
    try:
        img = schematic(block_id, json.dumps(params, sort_keys=True))
    except (KeyError, schematics.DrawingMismatch) as e:
        st.warning(f"No schematic shown: {e}")
        return
    st.image(img["png"], width="stretch")
    c1, c2 = st.columns(2)
    name = f"schematic_{pos}_{block_id}_step{n}"
    c1.download_button("Download PNG", img["png"], file_name=f"{name}.png", mime="image/png",
                       on_click="ignore", width="stretch", key=f"png-{pos}-{n}")
    c2.download_button("Download SVG", img["svg"], file_name=f"{name}.svg", mime="image/svg+xml",
                       on_click="ignore", width="stretch", key=f"svg-{pos}-{n}")
    with st.expander("Full size"):
        b64 = base64.b64encode(img["png"]).decode()
        st.markdown(f"<div style='overflow-x:auto'><img src='data:image/png;base64,{b64}' style='max-width:none'></div>",
                    unsafe_allow_html=True)


def card(title: str, body: str = "") -> None:
    st.markdown(f'<div class="card"><h4>{title}</h4>{body}</div>', unsafe_allow_html=True)


def esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def do(action, *args, **kw) -> bool:
    """Call a backend action; keep the reason to show if it is refused. True on success."""
    try:
        action(*args, **kw)
    except (actions.Busy, actions.WrongState, ValueError) as e:
        st.session_state["flash"] = str(e)
        return False
    except Exception as e:                                   # e.g. no CLAUDE_CODE_OAUTH_TOKEN for the real LLM
        st.session_state["flash"] = f"{type(e).__name__}: {e}"
        return False
    index.clear()
    return True


def refresh_while_working(run) -> None:
    """Re-run the page every REFRESH_S while this run's worker holds the lock."""
    a = actions.active(STORE)
    if a and a.get("run_id") == run.run_id:
        time.sleep(REFRESH_S)
        st.rerun()


STORE = actions.RunStore(RUNS_DIR)
BUSY = actions.active(STORE)


# ---------- title ----------
cfg = load_config()
t1, t2 = st.columns([3, 2])
t1.markdown("## Guitar Pedal Agent\n<span class='muted'>Multi-agent analog pedal design with ngspice</span>",
            unsafe_allow_html=True)
t2.markdown(f"<div style='text-align:right; padding-top:18px'><span class='pill'>{esc(cfg['llm']['model_id'])}</span>"
            f"<span class='pill'>{esc(ngspice())}</span><span class='pill'>live{' · fake LLM' if LLM == 'fake' else ''}</span></div>",
            unsafe_allow_html=True)

left, center, right = st.columns([1, 2.4, 1], gap="medium")

# ---------- LEFT: create project (disabled) + saved circuits ----------
with left:
    with st.container(border=True):
        st.markdown("**Create new project**")
        with st.form("create", border=False):
            name = st.text_input("Project name", placeholder="e.g. Jazz Christmas")
            genre = st.pills("Genre", GENRES)
            describe = st.text_area("Describe the sound", placeholder="Warm, mid-forward lead…", height=80)
            reference = st.text_input("Reference (song or artist)")
            create = st.form_submit_button("Create and draft target spec", disabled=bool(BUSY), width="stretch")
        if BUSY:
            st.caption(f"A run is active ({BUSY['run_id']}); one run at a time.")
        if create:
            new_id = None
            try:
                new_id = actions.create_project(name, genre, describe, reference, llm=LLM, store=STORE)
            except (actions.Busy, ValueError) as e:
                st.session_state["flash"] = str(e)
            except Exception as e:                           # e.g. no CLAUDE_CODE_OAUTH_TOKEN
                st.session_state["flash"] = f"{type(e).__name__}: {e}"
            if new_id:
                index.clear()
                st.session_state["sel_run"], st.session_state["source"] = new_id, "Projects"
            st.rerun()
        if "flash" in st.session_state:
            st.error(st.session_state.pop("flash"))

    with st.container(border=True):
        st.markdown("**Saved circuits**")
        idx = index(RUNS_DIR)
        source = st.radio("Show", ["Projects", "Benchmark runs"], horizontal=True, label_visibility="collapsed",
                          key="source")
        rows = [e for e in idx if (e["set"] is None) == (source == "Projects")]
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
            if source == "Benchmark runs" else (lambda e: f"{e['name']} · {e['chain']} · {e['n_pass']}/{e['n_targets']}" + (" · ⚑ illustrative" if e['illustrative'] else ""))
        by_id = {e["run_id"]: e for e in rows}
        ids = list(by_id)
        sel = st.session_state.get("sel_run")
        chosen_id = st.radio("Run", ids, index=ids.index(sel) if sel in ids else 0, format_func=lambda i: label(by_id[i]),
                             label_visibility="collapsed", key=f"pick-{source}-{len(ids)}")   # new key when a run is added
        st.session_state["sel_run"] = chosen_id
        st.caption(f"{len(idx)} runs indexed")

entry = by_id[chosen_id]
run = data.load_run(entry["path"])
steps = data.simulated_steps(run)
live = run.benchmark is None and not data.is_illustrative(run.run_id)   # actions only on real project runs
working = bool(BUSY) and BUSY.get("run_id") == run.run_id

# ---------- CENTER ----------
with center:
    if working:
        last = run.steps[-1].title if run.steps else "Tone Analyst drafting the target spec"
        st.info(f"Agent working… latest step: {last} · {run.sims_used}/{run.sim_budget} simulations "
                f"(this page refreshes every {REFRESH_S} s)")
    elif live and run.status == "running":
        st.warning("This run is marked running but no worker is active (it may have been interrupted).")
    if run.status == "awaiting_spec_approval" and live and not working:
        with st.container(border=True):
            st.markdown(f"**Approve the target spec** · {esc(run.project_id)}")
            st.markdown(f"<div class='muted'>{esc(run.spec.goal_text)}</div>", unsafe_allow_html=True)
            ta = next((s for s in run.steps if s.agent == "tone_analyst"), None)
            if ta:
                st.caption(f"Tone Analyst: {ta.why}")
            spec_df = pd.DataFrame([{"label": t.label, "metric": t.name, "lo": t.lo, "hi": t.hi, "unit": t.unit}
                                    for t in run.spec.targets])
            edited = st.data_editor(spec_df, hide_index=True, width="stretch", key=f"spec-{run.run_id}",
                                    disabled=["label", "metric", "unit"],
                                    column_config={"lo": st.column_config.NumberColumn("lo", format="%g"),
                                                   "hi": st.column_config.NumberColumn("hi", format="%g")})
            st.caption("Edit lo/hi if needed (empty = no bound), then approve. The agent starts designing after approval.")
            a1, a2 = st.columns(2)
            if a1.button("Approve targets", type="primary", width="stretch", disabled=bool(BUSY)):
                targets = None
                if not edited[["lo", "hi"]].equals(spec_df[["lo", "hi"]]):
                    targets = [t.model_dump(mode="json") | {"lo": None if pd.isna(r.lo) else float(r.lo),
                                                            "hi": None if pd.isna(r.hi) else float(r.hi)}
                               for t, r in zip(run.spec.targets, edited.itertuples())]
                do(actions.approve_spec, run.run_id, targets, llm=LLM, store=STORE)
                st.rerun()
            if a2.button("Reject", width="stretch", disabled=bool(BUSY)):
                do(actions.reject_spec, run.run_id, llm=LLM, store=STORE)
                st.rerun()
    default = data.display_step(run)
    if not steps:
        if run.status != "awaiting_spec_approval":
            st.info("This run has no simulated step yet.")
        refresh_while_working(run)
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
    # 1. project header, 2. signal chain
    card("Selected project",
         f"<div style='font-size:1.4rem; font-weight:600'>{esc(h['name'])}</div>"
         f"<div class='muted' style='margin:4px 0 10px'>{esc(h['goal'])}</div>{badges}")
    card(f"Signal chain · step {step.n}",
         f"<div class='chain'><div class='node'>{esc(data.pickup_text())}</div>{chain}"
         f"<span class='arrow'>→</span><div class='node'>{esc(data.amp_text())}</div></div>"
         f"<div class='muted' style='margin-top:6px'>Highlighted knob values were set by the agent; others are block defaults.</div>")

    # 3. block schematics, one per block
    for i, b in enumerate(step.candidate.chain, start=1):
        with st.container(border=True):
            st.markdown(f"**Block schematic** · {i}/{len(step.candidate.chain)} · `{b.block_id}` · step {step.n}")
            show_schematic(i, b.block_id, b.params, step.n)

    # 4. demo sound and feedback (accept, export)
    d1, d2 = st.columns(2)                                   # equal height: both cards stretch to the row
    with d1.container(border=True, height="stretch"):
        st.markdown("**Demo sound**")
        st.selectbox("Clip", ["DI clip (Phase 6)"], disabled=True)
        st.segmented_control("Signal", ["Dry", "Processed"], disabled=True)
        st.button("▶ Play", disabled=True, help="Audio rendering comes in Phase 6.")
    with d2.container(border=True, height="stretch"):
        st.markdown("**Feedback**")
        can = live and run.status == "awaiting_feedback" and not BUSY
        text = st.text_area("Tell the Planner what to change", disabled=not can, height=80, key=f"fb-{run.run_id}")
        b1, b2 = st.columns(2)
        if b1.button("Send to Planner", disabled=not can, width="stretch"):
            do(actions.send_feedback, run.run_id, text, llm=LLM, store=STORE)
            st.rerun()
        if b2.button("Accept design", disabled=not can, width="stretch"):
            do(actions.accept, run.run_id, store=STORE)
            st.rerun()
        if not live:
            st.caption("Read-only: " + ("benchmark run." if run.benchmark else "illustrative example."))
        elif run.status == "accepted":
            folder = actions.export_folder(run.run_id, STORE)
            if folder.exists():
                st.caption(f"Design accepted and exported to {folder}")
                for i, f in enumerate(sorted(folder.iterdir())):
                    st.download_button(f"Download {f.name}", f.read_bytes(), file_name=f.name, key=f"dl-{i}",
                                       width="stretch")
            else:
                st.caption("Design accepted.")
                if st.button("Export design (netlist, BOM, summary)", type="primary", width="stretch"):
                    do(actions.export_design, run.run_id, store=STORE)
                    st.rerun()
        elif BUSY and not working:
            st.caption(f"Another run is active ({BUSY['run_id']}).")

    # 5. test result
    with st.container(border=True):
        st.markdown(f"**Test result** · step {step.n}")
        p = step.report.plots
        g1, g2 = st.columns(2)
        if p:
            g1.altair_chart(waveform_chart(p), width="stretch")
            g2.altair_chart(response_chart(p), width="stretch")
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

    # 6. design choices: fixed-height box, opens scrolled to the newest step (earlier steps above)
    st.markdown("**Design choices**")
    with st.container(height=SCROLL_HEIGHT, border=True, autoscroll=True):
        html = ""
        for c in data.design_choices(run):
            res = f" · {c['n_pass']}/{h['n_targets']} targets" if c["simulated"] else ""
            errs = f"<div class='muted'>Rejected: {esc('; '.join(c['errors']))}</div>" if c["errors"] else ""
            tags = [c["action"]] + ([c["tag"]] if c["tag"] != c["action"] else [])
            html += (f"<div class='step'><b>{c['n']}. {esc(c['title'])}</b>"
                     + "".join(f"<span class='tag'>{esc(t)}</span>" for t in tags) + f"<span class='muted'>{res}</span>"
                     f"<div class='muted'>{esc(c['why'])}</div>{errs}</div>")
        st.markdown(html, unsafe_allow_html=True)

    # 7. component lists, per block, in one fixed-height scrolling box
    st.markdown(f"**Component list** · step {step.n}")
    with st.container(height=SCROLL_HEIGHT, border=True):
        for i, b in enumerate(step.candidate.chain, start=1):
            st.markdown(f"{i}/{len(step.candidate.chain)} · `{b.block_id}`")
            comps = pd.DataFrame(data.components(b.block_id, b.params))
            styled = comps[["designator", "kind", "value", "parameter", "note"]].style.apply(
                lambda r: [f"background-color: {ORANGE_LIGHT}" if comps.loc[r.name, "adjustable"] else ""] * len(r), axis=1)
            st.dataframe(styled, hide_index=True, width="stretch", height=35 * (len(comps) + 1) + 3)   # all rows
    st.caption("Highlighted rows are parameters the agent can change.")

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
            f"<tr><td>API-equivalent cost<br><span class='muted'>no per-token billing</span></td><td align='right'>{esc(a['cost'])}</td></tr>"
            + (f"<tr><td>Benchmark</td><td align='right'>{esc(a['benchmark']['set'])} {esc(a['benchmark']['target'])} "
               f"(cat. {esc(a['benchmark']['category'])}), seed {a['seed']}</td></tr>" if a["benchmark"] else "")
            + "</table>", unsafe_allow_html=True)
        st.markdown("**Repeated runs (same goal)**")
        rep = data.repeated_runs(index(RUNS_DIR), entry)
        if rep:
            med = rep["median_sims_to_success"]
            st.markdown(f"<div class='muted'>{rep['successes']} of {rep['runs']} runs succeeded "
                        f"({100 * rep['success_rate']:.0f} %)<br>median simulations to success: "
                        f"{'–' if med is None else f'{med:g}'}<br>median simulations used: {rep['median_sims_used']:g}</div>",
                        unsafe_allow_html=True)
        else:
            st.caption("Only one run with this goal and mode.")

refresh_while_working(run)
