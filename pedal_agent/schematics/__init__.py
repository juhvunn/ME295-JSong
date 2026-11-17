"""Block schematics (Phase 4): one drawing module per block, values taken from the rendered netlist.

    draw(block_id, params) -> Sketch            finished drawing (labels, stage boxes, caption)
    images(block_id, params) -> {"png", "svg"}  checked drawing as bytes (dashboard and export)
    python -m pedal_agent.schematics <block_id> [name=value ...] --out file.png|.svg

tests/test_schematics.py checks every drawing against its netlist (pedal_agent/schematics/common.py).
"""
import importlib

from pedal_agent.schematics.common import Sketch, caption, check_drawing

BLOCKS = ("od_ts808", "dist_distplus", "fuzz_ff_si")


class DrawingMismatch(RuntimeError):
    """The drawing does not match the block's rendered netlist (never shown or exported)."""


def sketch(block_id: str, params: dict | None = None) -> Sketch:
    """The drawing before labels and caption are finalised (used by the connectivity check)."""
    if block_id not in BLOCKS:
        raise KeyError(f"no schematic for block {block_id}")
    sk = Sketch(block_id, dict(params or {}))
    importlib.import_module(f"pedal_agent.schematics.{block_id}").draw(sk)
    return sk


def draw(block_id: str, params: dict | None = None) -> Sketch:
    sk = sketch(block_id, params)
    return sk.finish(caption(sk))


def images(block_id: str, params: dict | None = None) -> dict:
    """{"png": bytes, "svg": bytes, "netlist": the block's rendered subcircuit}; raises DrawingMismatch if the
    drawing's connections differ from the netlist, KeyError if the block has no schematic."""
    sk = sketch(block_id, params)
    if problems := check_drawing(sk):
        raise DrawingMismatch(f"{block_id}: " + "; ".join(problems))
    sk.finish(caption(sk))
    return {"png": sk.image("png"), "svg": sk.image("svg"), "netlist": sk.netlist}


__all__ = ["BLOCKS", "DrawingMismatch", "Sketch", "check_drawing", "draw", "images", "sketch"]
