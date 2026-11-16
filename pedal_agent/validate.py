"""Validate: deterministic checks on a proposed chain before any simulation.

Errors reject the candidate (no sim budget used; the errors go back to the
Planner). Fixes and soft rules become warnings: component values are snapped to
their E-series, the action label is derived from the actual chain change, and a
block with prefers_first: true that is not first is flagged.
"""
import math
from dataclasses import dataclass, field

from pedal_agent.build import BLOCKS_DIR, load_block, parse_value
from pedal_agent.schemas import BlockInstance, Candidate

MAX_CHAIN = 3

E_SERIES = {
    "E6": [1.0, 1.5, 2.2, 3.3, 4.7, 6.8],
    "E12": [1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2],
    "E24": [1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
            3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1],
}


@dataclass
class ValidationResult:
    candidate: Candidate | None         # normalized (snapped) chain; None if there are errors
    action: str | None                  # action derived from the chain change
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def block_ids() -> list[str]:
    return sorted(p.name for p in BLOCKS_DIR.iterdir() if (p / "block.yaml").is_file())


def snap(value: float, series: str, lo: float, hi: float) -> float:
    """Nearest E-series value (log distance) within [lo, hi]."""
    base = E_SERIES[series]
    options = [m * 10.0 ** d for d in range(math.floor(math.log10(lo)) - 1, math.ceil(math.log10(hi)) + 1)
               for m in base]
    options = [v for v in options if lo * (1 - 1e-9) <= v <= hi * (1 + 1e-9)]
    return min(options, key=lambda v: abs(math.log(v / value)))


def check_params(blk: BlockInstance, meta: dict) -> tuple[dict, list[str], list[str]]:
    params, errors, warnings = {}, [], []
    spec_all = meta["params"]
    for name, value in blk.params.items():
        where = f"{blk.block_id}.{name}"
        spec = spec_all.get(name)
        if spec is None:
            errors.append(f"{where}: unknown parameter; allowed: {sorted(spec_all)}")
            continue
        if spec["type"] == "choice":
            if value not in spec["choices"]:
                errors.append(f"{where}={value!r}: not one of {spec['choices']}")
            else:
                params[name] = value
            continue
        try:
            x = parse_value(value)
        except (TypeError, ValueError):
            errors.append(f"{where}={value!r}: expected a number")
            continue
        if not math.isfinite(x):
            errors.append(f"{where}={value!r}: expected a finite number")
        elif spec["type"] == "pot":
            if not 0.0 <= x <= 1.0:
                errors.append(f"{where}={x:g}: knob position must be in [0, 1]")
            else:
                params[name] = x
        else:  # component
            lo, hi = parse_value(spec["min"]), parse_value(spec["max"])
            if not lo <= x <= hi:
                errors.append(f"{where}={x:g}: outside [{spec['min']}, {spec['max']}]")
                continue
            s = snap(x, spec["series"], lo, hi) if spec.get("series") else x
            if abs(s - x) > 1e-3 * x:
                warnings.append(f"{where}: {x:g} snapped to {s:g} ({spec['series']})")
            params[name] = float(f"{s:.6g}")
    return params, errors, warnings


def derive_action(previous: list[str] | None, proposed: list[str]) -> str:
    if previous is None:
        return "initial_chain"
    if proposed == previous:
        return "adjust_params"
    if len(proposed) == len(previous) + 1:
        return "add_block"
    if len(proposed) == len(previous) - 1:
        return "remove_block"
    return "swap_block"


def validate(candidate: Candidate, claimed_action: str, previous_chain: list[str] | None,
             mode: str = "agent") -> ValidationResult:
    """previous_chain: block ids of the last valid candidate (None before the first one)."""
    ids = [b.block_id for b in candidate.chain]
    errors, warnings = [], []
    if not 1 <= len(ids) <= MAX_CHAIN:
        errors.append(f"chain must have 1-{MAX_CHAIN} blocks, got {len(ids)}")
    known = block_ids()
    for b in ids:
        if b not in known:
            errors.append(f"unknown block {b!r}; allowed: {known}")
    dupes = sorted({b for b in ids if ids.count(b) > 1})
    if dupes:
        errors.append(f"each block may appear at most once; repeated: {dupes}")

    action = derive_action(previous_chain, ids)
    if mode == "baseline_fixed_topology" and previous_chain is not None and ids != previous_chain:
        errors.append(f"baseline_fixed_topology: the chain must stay {previous_chain}; "
                      "only adjust_params is allowed")
    elif claimed_action != action:
        warnings.append(f"action relabelled {claimed_action} -> {action} from the chain change")

    chain = []
    for pos, blk in enumerate(candidate.chain):
        if blk.block_id not in known:
            continue
        _, meta = load_block(blk.block_id)
        params, e, w = check_params(blk, meta)
        errors += e
        warnings += w
        if meta.get("prefers_first") and pos > 0:
            warnings.append(f"{blk.block_id} is not first in the chain: {meta.get('chain_hint', '')}".strip())
        chain.append(BlockInstance(block_id=blk.block_id, params=params))

    if errors:
        return ValidationResult(None, None, errors, warnings)
    return ValidationResult(Candidate(chain=chain, rationale=candidate.rationale), action, errors, warnings)


def fingerprint(candidate: Candidate) -> tuple:
    """Identity of a (validated) chain with defaults filled in, for duplicate detection."""
    out = []
    for blk in candidate.chain:
        _, meta = load_block(blk.block_id)
        full = {}
        for name, spec in meta["params"].items():
            v = blk.params.get(name, spec.get("default", spec.get("value")))
            full[name] = v if spec["type"] == "choice" else round(parse_value(v), 9)
        out.append((blk.block_id, tuple(sorted(full.items()))))
    return tuple(out)
