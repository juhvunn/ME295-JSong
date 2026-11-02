"""build_netlist: fill a trusted template with numeric parameter values.

Only templates in src/tools/templates/ are used, and every value must be a finite
number, so no LLM-generated text ever reaches the netlist.
"""
import math
import re
from pathlib import Path
from string import Template

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
PLACEHOLDER_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")


def build_netlist(template_name: str, params: dict[str, float]) -> str:
    path = TEMPLATES_DIR / template_name
    if path.parent != TEMPLATES_DIR or not path.is_file():
        raise ValueError(f"unknown template {template_name!r}")
    text = path.read_text(encoding="utf-8")

    required = set(PLACEHOLDER_RE.findall(text))
    if set(params) != required:
        raise ValueError(
            f"{template_name}: missing {sorted(required - set(params))}, "
            f"unexpected {sorted(set(params) - required)}"
        )

    formatted = {}
    for name, value in params.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name}: expected a finite number, got {value!r}")
        formatted[name] = f"{value:.6g}"
    return Template(text).substitute(formatted)
