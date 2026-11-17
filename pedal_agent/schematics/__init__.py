"""Block schematics (Phase 4): one drawing module per block, values taken from the rendered netlist.

    draw(block_id, params) -> Sketch            finished drawing (labels, stage boxes, caption)
    python -m pedal_agent.schematics <block_id> [name=value ...] --out file.png|.svg

tests/test_schematics.py checks every drawing against its netlist (pedal_agent/schematics/common.py).
"""
import importlib

from pedal_agent.schematics.common import Sketch, caption, check_drawing

BLOCKS = ("od_ts808", "dist_distplus", "fuzz_ff_si")


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


__all__ = ["BLOCKS", "Sketch", "check_drawing", "draw", "sketch"]
