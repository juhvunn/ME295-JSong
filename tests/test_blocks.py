"""Block library consistency (no simulation)."""
import typing

import pytest

from pedal_agent.build import BLOCKS_DIR, load_block
from pedal_agent.schemas import MetricName
from scripts.fill_typical_metrics import variants

BLOCK_IDS = sorted(p.name for p in BLOCKS_DIR.iterdir() if p.is_dir())


@pytest.mark.parametrize("block_id", BLOCK_IDS)
def test_typical_metrics_cover_every_choice_and_metric(block_id):
    _, meta = load_block(block_id)
    keys = {",".join(f"{k}={v}" for k, v in o.items()) or "default" for o in variants(meta)}
    assert set(meta["typical_metrics"]) == keys
    for m in meta["typical_metrics"].values():
        assert set(m) == set(typing.get_args(MetricName))
