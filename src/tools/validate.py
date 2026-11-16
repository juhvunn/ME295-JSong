"""validate_circuit: deterministic structural checks on a candidate."""
import math

import yaml

from src.config import REPO_ROOT, load_config


def load_block_library() -> dict:
    with open(REPO_ROOT / load_config()["blocks"], encoding="utf-8") as f:
        return yaml.safe_load(f)["blocks"]


def validate_circuit(candidate: dict, library: dict | None = None) -> list[str]:
    """Return a list of problems with {"block": name, "values": {param: number}}; empty if valid.

    v1 candidates are a single catalog block. Checks: the block exists and has a
    template, the values cover exactly its parameters, and each value is a finite
    number inside the catalog range.
    """
    library = library if library is not None else load_block_library()
    name = candidate.get("block")
    if name not in library:
        return [f"unknown block {name!r}; allowed: {sorted(library)}"]
    block = library[name]
    if not block.get("template"):
        return [f"block {name!r} has no netlist template yet"]

    values = candidate.get("values") or {}
    params = block["params"]
    errors = []
    for missing in sorted(set(params) - set(values)):
        errors.append(f"{name}: missing parameter {missing}")
    for extra in sorted(set(values) - set(params)):
        errors.append(f"{name}: unexpected parameter {extra}")
    for param, spec in params.items():
        if param not in values:
            continue
        value = values[param]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            errors.append(f"{name}.{param}: expected a finite number, got {value!r}")
        elif not spec["min"] <= value <= spec["max"]:
            errors.append(f"{name}.{param}={value:g} {spec['unit']} outside [{spec['min']:g}, {spec['max']:g}]")
    return errors
