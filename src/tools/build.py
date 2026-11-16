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


def load_protocol() -> dict:
    import yaml

    from src.config import REPO_ROOT, load_config

    config = load_config()
    with (REPO_ROOT / config["protocol"]).open(encoding="utf-8") as protocol_file:
        return yaml.safe_load(protocol_file)


def protocol_parameters() -> dict[str, float]:
    """Return the template placeholders that come from the shared protocol."""
    protocol = load_protocol()
    ac, transient = protocol["ac"], protocol["transient"]
    return {
        "VIN_AMP": transient["amplitude_v"],
        "FREQ": transient["freq_hz"],
        "AC_PPD": ac["points_per_decade"],
        "AC_FSTART": ac["f_start_hz"],
        "AC_FSTOP": ac["f_stop_hz"],
        "TSTEP": transient["t_step_s"],
        "TSTOP": transient["t_stop_s"],
    }


def diode_clipper_parameters() -> dict[str, float]:
    """Return the shared component and protocol parameters for the clipper."""
    return {"R1": 4.7e3, "C1": 10e-9, **protocol_parameters()}


def build_block_netlist(template_name: str, values: dict[str, float]) -> str:
    """Fill a block template with component values plus the protocol placeholders it uses."""
    path = TEMPLATES_DIR / template_name
    if path.parent != TEMPLATES_DIR or not path.is_file():
        raise ValueError(f"unknown template {template_name!r}")
    required = set(PLACEHOLDER_RE.findall(path.read_text(encoding="utf-8")))
    shared = {k: v for k, v in protocol_parameters().items() if k in required}
    return build_netlist(template_name, {**shared, **values})
