"""Block schematics (pedal_agent/schematics): the drawing matches the rendered netlist part for part and node for
node, for defaults, every choice value, pot end stops and component limits; labels are the simulated values."""
import inspect
import types

import pytest

from pedal_agent.build import load_block, parse_value
from pedal_agent.schematics import BLOCKS, check_drawing, draw, sketch
from pedal_agent.schematics import od_ts808
from pedal_agent.schematics.common import PART_NAME, Sketch, value_text


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
    sk = sketch("od_ts808", {"drive": 0.8, "tone": 0.2, "level": 0.7, "C3": "100n", "D_clip": "led"})
    lab, v = sk.labels, lambda d: value_text(sk.parts[d][3])
    assert lab["C3"] == "C3\n100n" and lab["R9"] == "R9\n10k" and lab["R22"] == "R22\n1.5M"
    assert lab["R19"] == f"R19 500k log\ndrive 0.80 (1 = max drive)\nset to {v('R19')}"
    # one convention: segments named by their ends on the page, upper (or left) segment first
    assert lab["R20"].endswith(f"left-wiper {v('R20A')} / wiper-right {v('R20B')}")      # R20A: t1 (left) - wiper
    assert lab["R21"].endswith(f"top-wiper {v('R21B')}\nwiper-bottom {v('R21A')}")       # R21B: v1 (top) - wiper
    assert v("R21B") == "30k" and v("R21A") == "70k"                                      # level 0.70, linear
    assert lab["D3"] == "D3\nred LED" and lab["X1A"] == "JRC4558 (1/2)" and "D1" not in sk.parts
    fz = sketch("fuzz_ff_si", {"fuzz": 0.9, "Q_model": "Q2N3904"})
    assert "fuzz 0.90\n(1 = wiper at Q2 emitter, max fuzz)" in fz.labels["R6"]
    assert fz.labels["R6"].endswith(f"top-wiper {value_text(fz.parts['R6A'][3])}\n"
                                    f"wiper-bottom {value_text(fz.parts['R6B'][3])}")    # R6A: e2 (top) - wiper
    assert fz.labels["Q1"] == "Q1\n2N3904"
    ds = sketch("dist_distplus", {"gain": 0.8})
    assert ds.labels["R7"] == f"R7 500k log\ngain 0.80 (1 = max gain)\nset to {value_text(ds.parts['R7'][3])}"
    assert value_text(ds.parts["R7"][3]) == "8.8k"


@pytest.mark.parametrize("block_id", BLOCKS)
def test_every_model_has_a_readable_name(block_id):
    """Drawings show part names, never SPICE model names, for every choice value."""
    for params in settings(block_id):
        sk = sketch(block_id, params)
        for des in sk.parts:
            if des[0] in "DQX":
                model = sk.parts[des][3] if des[0] == "D" else sk.parts[des][4] if des[0] == "Q" else sk.parts[des][-1]
                assert model in PART_NAME and PART_NAME[model] in sk.labels[des], (des, model)


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
