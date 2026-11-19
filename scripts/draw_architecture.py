"""Architecture figure for the README: docs/architecture.png and .svg (matplotlib only).

The boxes and arrows follow the LangGraph wiring in pedal_agent/graph.py (tone_analyst -> approve_spec ->
planner -> validate -> check -> router -> planner | feedback -> planner | accept) plus export and demo sound.

Usage: python -m scripts.draw_architecture
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

from pedal_agent.config import REPO_ROOT  # noqa: E402

KIND = {"llm": ("#fde9df", "#eb6834", "Claude (LLM)"), "human": ("#e3eefb", "#2a78d6", "Human"),
        "code": ("#f1f0eb", "#8a8982", "Deterministic code"), "data": ("#ffffff", "#b5b4ad", "Files")}
LINE = "#5f5e58"


def box(ax, x, y, text, kind, w=2.4, h=0.9):
    fill, edge, _ = KIND[kind]
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                fc=fill, ec=edge, lw=1.6, ls="--" if kind == "data" else "-"))
    ax.text(x, y, text, ha="center", va="center", fontsize=9.5, color="#2b2b28", linespacing=1.35)


def path(ax, pts, label="", at=None, va="bottom"):
    """Right-angled connector through pts, arrowhead at the last point; label at `at`."""
    xs, ys = zip(*pts)
    ax.plot(xs[:-1], ys[:-1], color=LINE, lw=1.3, solid_capstyle="round")
    ax.add_patch(FancyArrowPatch(pts[-2], pts[-1], arrowstyle="-|>", mutation_scale=13, lw=1.3, color=LINE,
                                 shrinkA=0, shrinkB=1))
    if label:
        ax.text(*at, label, ha="center", va=va, fontsize=8.3, color="#4a4944")


def main() -> int:
    fig, ax = plt.subplots(figsize=(13, 6.6))
    ax.set_xlim(0, 13)
    ax.set_ylim(-0.15, 6.45)
    ax.axis("off")
    X = [1.8, 4.75, 7.7, 10.65]
    y1, y2, y3 = 5.3, 3.2, 1.0
    # spec
    box(ax, X[0], y1, "Tone goal\n\"warm crunch\"", "human")
    box(ax, X[1], y1, "Tone Analyst\ngoal → metric targets", "llm")
    box(ax, X[2], y1, "Approve spec\nedit the target ranges", "human")
    box(ax, 11.6, y1, "RunRecord per run\nruns/<run_id>.json\nevery step → dashboard", "data", w=2.3, h=1.0)
    path(ax, [(X[0] + 1.2, y1), (X[1] - 1.2, y1)])
    path(ax, [(X[1] + 1.2, y1), (X[2] - 1.2, y1)])
    # design loop
    box(ax, X[0], y2, "Planner\n1–3 blocks + values\nfrom the block catalog", "llm", h=1.2)
    box(ax, X[1], y2, "Validate\nranges, choices,\nchain rules", "code", h=1.2)
    box(ax, X[2], y2, "Checker\nnetlist from templates and\nfitted models → ngspice\n→ metrics → score", "code",
        h=1.2)
    box(ax, X[3], y2, "Router\nall targets met?\nbudget used?", "code", h=1.2)
    top, bottom = y2 + 0.6, y2 - 0.6
    path(ax, [(X[2], y1 - 0.45), (X[2], 4.5), (1.35, 4.5), (1.35, top)], "approved target spec", (4.6, 4.52))
    path(ax, [(X[0] + 1.2, y2), (X[1] - 1.2, y2)])
    path(ax, [(X[1] + 1.2, y2), (X[2] - 1.2, y2)], "valid", ((X[1] + X[2]) / 2, y2 + 0.05))
    path(ax, [(X[2] + 1.2, y2), (X[3] - 1.2, y2)])
    path(ax, [(X[3], top), (X[3], 4.12), (2.25, 4.12), (2.25, top)],
         "revise: per metric range, measured value, status, score → change topology or values", (6.2, 4.14))
    path(ax, [(X[1], bottom), (X[1], 2.2), (X[3] - 0.45, 2.2), (X[3] - 0.45, bottom)],
         "invalid: errors go back to the Planner, no simulation used", (7.7, 2.16), va="top")
    # human review and outputs
    box(ax, X[3], y3, "Feedback\ntext or accept", "human")
    box(ax, 7.7, y3, "Accept", "human", w=1.4)
    box(ax, 4.2, y3, "Export: netlist, BOM,\nschematics, summary\n+ demo sound (WAV)", "code", w=3.0, h=1.0)
    path(ax, [(X[3] + 0.45, bottom), (X[3] + 0.45, y3 + 0.45)], "targets met\nor budget used", (X[3] + 1.35, 1.85))
    path(ax, [(X[3] - 1.2, y3), (8.4, y3)])
    path(ax, [(7.0, y3), (5.7, y3)])
    path(ax, [(X[3], y3 - 0.45), (X[3], 0.15), (0.3, 0.15), (0.3, y2), (X[0] - 1.2, y2)],
         "text feedback → Planner again", (6.2, 0.12), va="top")
    # legend
    for i, k in enumerate(["llm", "human", "code", "data"]):
        fill, edge, label = KIND[k]
        x0 = 0.6 + 2.4 * i
        ax.add_patch(FancyBboxPatch((x0, 6.12), 0.35, 0.22, boxstyle="round,pad=0.01", fc=fill, ec=edge,
                                    lw=1.4, ls="--" if k == "data" else "-"))
        ax.text(x0 + 0.5, 6.23, label, va="center", fontsize=9.5)
    out = REPO_ROOT / "docs" / "architecture"
    fig.savefig(out.with_suffix(".png"), dpi=150, bbox_inches="tight")
    fig.savefig(out.with_suffix(".svg"), bbox_inches="tight")
    print("wrote", out.with_suffix(".png"), out.with_suffix(".svg"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
