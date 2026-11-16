"""Before/after table: every block at its defaults, once per choice combination, with the
placeholder ("smoke") and the real model set. Changes no files.

Usage: python -m scripts.compare_models
"""
import sys

import pedal_agent.checker as checker
from pedal_agent.build import BLOCKS_DIR, load_block
from pedal_agent.schemas import BlockInstance, Candidate, TargetSpec
from scripts.fill_typical_metrics import variants

KEYS = (("gain_1k_db", "{:.2f}"), ("thd_pct", "{:.1f}"), ("ac_peak_hz", "{:.0f}"), ("even_odd", "{:.3f}"),
        ("out_pk_v", "{:.3f}"))


def run(block: str, overrides: dict, model_set: str):
    checker.MODEL_SET = model_set
    try:
        return checker.check(Candidate(chain=[BlockInstance(block_id=block, params=overrides)], rationale=""),
                             TargetSpec(goal_text="", targets=[]))
    finally:
        checker.MODEL_SET = None


def main() -> int:
    print("| Block | Choice | Models | DC | " + " | ".join(k for k, _ in KEYS) + " | flagged |")
    print("|---|---|---|---|" + "---|" * len(KEYS) + "---|")
    for block in sorted(p.name for p in BLOCKS_DIR.iterdir() if p.is_dir()):
        _, meta = load_block(block)
        for overrides in variants(meta):
            label = ",".join(f"{k}={v}" for k, v in overrides.items()) or "default"
            defaults = {k: meta["params"][k]["default"] for k in overrides}
            if overrides == defaults:
                label += " (default)"
            for model_set in ("smoke", "real"):
                rep = run(block, overrides, model_set)
                dc = "ok" if rep.dc_ok else "FAIL: " + "; ".join(e.split(" outside")[0] for e in rep.errors)
                vals = " | ".join(fmt.format(rep.metrics[k]) if k in rep.metrics else "-" for k, fmt in KEYS)
                print(f"| {block} | {label} | {model_set} | {dc} | {vals} | "
                      f"{'yes' if rep.placeholder_or_unvalidated else 'no'} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
