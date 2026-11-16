"""Random designs from the block catalog, shared by the AI-free baselines and the benchmark generator.

Rules (docs/phase3_plan.md): validated choices only; knobs uniform in [0.05, 0.95]; parts uniform
over the E-series values inside min/max; chains of 1-2 blocks, no block twice, a block with
prefers_first (fuzz_ff_si) placed first. Every draw comes from the given random.Random, so a seed
reproduces the sequence exactly.
"""
import random

from pedal_agent.build import load_block, parse_value
from pedal_agent.validate import allowed_choices, block_ids, series_values

KNOB_RANGE = (0.05, 0.95)
MAX_CHAIN = 2


def sample_params(block_id: str, rng: random.Random) -> dict:
    _, meta = load_block(block_id)
    params = {}
    for name in sorted(meta["params"]):                      # sorted: draw order does not depend on YAML order
        spec = meta["params"][name]
        if spec["type"] == "pot":
            params[name] = round(rng.uniform(*KNOB_RANGE), 3)
        elif spec["type"] == "choice":
            params[name] = rng.choice(allowed_choices(spec, allow_unvalidated=False))
        else:
            lo, hi = parse_value(spec["min"]), parse_value(spec["max"])
            params[name] = rng.choice(series_values(spec["series"], lo, hi)) if spec.get("series") \
                else float(f"{rng.uniform(lo, hi):.6g}")
    return params


def order_chain(ids: list[str]) -> list[str]:
    """Blocks with prefers_first go first (keeps random draws free of chain-order warnings)."""
    first = [b for b in ids if load_block(b)[1].get("prefers_first")]
    return first + [b for b in ids if b not in first]


def sample_chain(rng: random.Random, max_len: int = MAX_CHAIN) -> list[str]:
    n = rng.randint(1, max_len)
    return order_chain(rng.sample(block_ids(), n))


def sample_design(rng: random.Random, chain: list[str] | None = None) -> list[tuple[str, dict]]:
    """[(block_id, params)]; random chain unless one is given."""
    return [(b, sample_params(b, rng)) for b in (chain or sample_chain(rng))]


# ---------- benchmark generator distribution (docs/phase3_plan.md 4b (a)): deliberately different ----------
GEN_DEFAULT_CHOICE_P = 0.25


def generator_params(block_id: str, rng: random.Random) -> dict:
    """Knobs arcsine (Beta(0.5, 0.5)) over [0, 1]; default choice 25 %, the other validated choices
    share 75 %; parts log-uniform over [min, max] snapped to their E-series."""
    import math

    from pedal_agent.validate import snap

    _, meta = load_block(block_id)
    params = {}
    for name in sorted(meta["params"]):
        spec = meta["params"][name]
        if spec["type"] == "pot":
            params[name] = round(rng.betavariate(0.5, 0.5), 3)
        elif spec["type"] == "choice":
            allowed = allowed_choices(spec, allow_unvalidated=False)
            others = [c for c in allowed if c != spec["default"]]
            params[name] = spec["default"] if (not others or rng.random() < GEN_DEFAULT_CHOICE_P) else rng.choice(others)
        else:
            lo, hi = parse_value(spec["min"]), parse_value(spec["max"])
            x = math.exp(rng.uniform(math.log(lo), math.log(hi)))
            params[name] = snap(x, spec["series"], lo, hi) if spec.get("series") else float(f"{x:.6g}")
    return params


def generator_design(rng: random.Random, chain: list[str]) -> list[tuple[str, dict]]:
    return [(b, generator_params(b, rng)) for b in chain]
