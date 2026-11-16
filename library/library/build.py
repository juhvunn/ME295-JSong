"""Render a block template into a SPICE subcircuit from normalized parameters."""
from pathlib import Path
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

LIB = Path(__file__).parent
R_MIN = 1.0  # ohm, avoid zero-ohm pot legs

SI = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "k": 1e3, "Meg": 1e6}

def parse_value(v):
    if isinstance(v, (int, float)):
        return float(v)
    for suf in sorted(SI, key=len, reverse=True):
        if v.endswith(suf):
            return float(v[: -len(suf)]) * SI[suf]
    return float(v)

def taper(x, kind):
    """Pot position x in [0,1] -> resistance fraction."""
    x = min(max(float(x), 0.0), 1.0)
    if kind == "linear":
        return x
    if kind == "log":  # audio (A) taper approx: 10% at mid-rotation
        a = 81.0
        return (a ** x - 1.0) / (a - 1.0)
    raise ValueError(kind)

def load_block(block_id):
    d = LIB / "blocks" / block_id
    return d, yaml.safe_load((d / "block.yaml").read_text())

def render(block_id, overrides=None):
    d, meta = load_block(block_id)
    vals = {k: p.get("default", p.get("value")) for k, p in meta["params"].items()}
    vals.update(overrides or {})
    ctx = dict(meta["models"])
    for name, p in meta["params"].items():
        v = vals[name]
        if p["type"] == "pot":
            # invert: knob position runs opposite to the A segment
            #   (e.g. reverse-log gain rheostat, fuzz wiper toward emitter)
            x = 1.0 - float(v) if p.get("invert") else float(v)
            rt, f = parse_value(p["r_total"]), taper(x, p["taper"])
            des = p["designator"]
            if p["mode"] == "rheostat":
                ctx[des] = f"{max(rt * f, R_MIN):.6g}"
            else:  # divider: A = end1-to-wiper = rt*f, B = wiper-to-end2
                ctx[des + "A"] = f"{max(rt * f, R_MIN):.6g}"
                ctx[des + "B"] = f"{max(rt * (1 - f), R_MIN):.6g}"
        elif p["type"] == "choice":
            if v not in p["choices"]:
                raise ValueError(f"{name}={v} not in {p['choices']}")
            ctx[name] = v
        else:
            ctx[name] = f"{parse_value(v):.6g}"
    env = Environment(loader=FileSystemLoader(d), undefined=StrictUndefined,
                      keep_trailing_newline=True)
    return env.get_template(meta["template"]).render(**ctx)
