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
    assert {k.split(" (recommended")[0] for k in meta["typical_metrics"]} == keys
    for m in meta["typical_metrics"].values():
        assert set(m) == set(typing.get_args(MetricName))


def test_recommended_r5_is_a_hint_only():
    """fuzz_ff_si recommends R5 = 5.6k for Q2N3904, but Build and Validate must not apply it."""
    import re
    from pedal_agent.build import render
    from pedal_agent.prompts import catalog
    from pedal_agent.schemas import BlockInstance, Candidate
    from pedal_agent.validate import validate

    _, meta = load_block("fuzz_ff_si")
    assert meta["params"]["Q_model"]["recommended"] == {"Q2N3904": {"R5": "5.6k"}}
    assert meta["params"]["R5"]["value"] == "8.2k"            # GGG default unchanged

    net = render("fuzz_ff_si", {"Q_model": "Q2N3904"})
    assert re.search(r"(?m)^R5\s+na\s+c2\s+8200\b", net)       # no automatic 5.6k
    assert "Q2N3904" in net

    res = validate(Candidate(chain=[BlockInstance(block_id="fuzz_ff_si", params={"Q_model": "Q2N3904"})],
                             rationale=""), "initial_chain", None)
    assert res.ok and res.candidate.chain[0].params == {"Q_model": "Q2N3904"}

    fuzz = next(b for b in catalog(include_typical=False) if b["id"] == "fuzz_ff_si")
    assert "Q2N3904 -> R5=5.6k" in fuzz["params"]["Q_model"] and "set them yourself" in fuzz["params"]["Q_model"]
