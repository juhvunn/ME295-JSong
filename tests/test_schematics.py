"""Block schematics (pedal_agent/schematics): the drawing matches the rendered netlist part for part and node for
node, for defaults, every choice value, pot end stops and component limits; labels are the simulated values."""
import inspect
import types

import pytest

from pedal_agent.build import load_block, parse_value
from pedal_agent.schematics import BLOCKS, check_drawing, draw, sketch
from pedal_agent.schematics import od_ts808
from pedal_agent.schematics.common import Sketch, value_text


def settings(block_id):
    """Defaults, each choice value, all pots at 0 and at 1, all components at min and at max."""
    params = load_block(block_id)[1]["params"]
    out = [{}]
    out += [{n: c} for n, p in params.items() if p["type"] == "choice" for c in p["choices"]]
    for x in (0.0, 1.0):
        out.append({n: x for n, p in params.items() if p["type"] == "pot"})
    for lim in ("min", "max"):
        out.append({n: p[lim] for n, p in params.items() if p["type"] == "component"})
    return out


CASES = [(b, s) for b in BLOCKS for s in settings(b)]


@pytest.mark.parametrize("block_id,params", CASES, ids=[f"{b}-{'-'.join(f'{k}={v}' for k, v in s.items()) or 'defaults'}"
                                                         for b, s in CASES])
def test_drawing_matches_netlist(block_id, params):
    assert check_drawing(sketch(block_id, params)) == []


MUTATIONS = {
    "diode drawn backwards": ('branch(ca, m1[1] + 7.2, reverse=True)', 'branch(ca, m1[1] + 7.2)'),
    "R16 to ground instead of Vr": ('s.vr((r16[0], r16[1] - 2), "down")', 's.gnd((r16[0], r16[1] - 2))'),
    "missing wire to the + input": ('s.wire(p1, xy(a, "in2"))', 'pass'),
    "part left out": ('    s.two("R11", (tap[0], tap[1] - 2), "down", side="right")\n', ''),
}


@pytest.mark.parametrize("name", MUTATIONS)
def test_check_catches_drawing_errors(name):
    src = inspect.getsource(od_ts808)
    old, new = MUTATIONS[name]
    assert src.count(old) == 1
    mod = types.ModuleType("mutant")
    exec(src.replace(old, new), mod.__dict__)
    sk = Sketch("od_ts808")
    try:
        mod.draw(sk)
    except Exception:
        return                                          # a broken layout that cannot even be drawn also fails
    assert check_drawing(sk), name


def test_labels_are_the_simulated_values():
    sk = sketch("od_ts808", {"drive": 0.8, "tone": 0.2, "C3": "100n", "D_clip": "led"})
    assert sk.label_of("C3") == "C3\n100n" and sk.label_of("R9") == "R9\n10k" and sk.label_of("R22") == "R22\n1.5M"
    assert value_text(sk.parts["R19"][3]) in sk.label_of("R19") and "drive 0.80" in sk.label_of("R19")
    a, b = value_text(sk.parts["R20A"][3]), value_text(sk.parts["R20B"][3])
    assert f"({a}/{b})" in sk.pot_label("R20") and parse_value(sk.parts["R20A"][3]) < parse_value(sk.parts["R20B"][3])
    assert sk.label_of("D3") == "D3\nDLED_RED" and "D1" not in sk.parts


def test_shaded_parts_are_the_adjustable_ones():
    assert sketch("od_ts808").adjustable == {"R19", "R20", "R21", "D1", "D2", "D3", "D4", "C3", "C4"}
    assert sketch("dist_distplus").adjustable == {"R7", "R10", "D1", "D2", "C4", "C7"}
    assert sketch("fuzz_ff_si").adjustable == {"R6", "R10", "Q1", "Q2", "R5", "C1"}


@pytest.mark.parametrize("block_id", BLOCKS)
def test_png_with_caption(tmp_path, block_id):
    from pedal_agent.schematics.common import caption
    sk = sketch(block_id)
    text = caption(sk)
    assert "redrawn; values as simulated" in text and "GGG" in text
    assert ("Op-amp supply pins" in text) == (block_id != "fuzz_ff_si")
    out = draw(block_id).save(tmp_path / f"{block_id}.png")
    assert out.stat().st_size > 20_000
