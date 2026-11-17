"""Shared drawing code for the block schematics (schemdraw, matplotlib backend, no display).

A block module only places parts and wires; every part value comes from the block's rendered netlist
(build.render with the run's parameters), so labels are the simulated values. The connectivity of the
drawing is recovered from its geometry (connections()) and tests/test_schematics.py checks it against the
netlist, node for node.

Conventions: tags (ground, +9V, Vr, ports) join every point with the same name; a wire joins its end points and
any terminal or wire end lying on it; crossing wires without a shared end point are not connected. Op-amp
supply pins are not drawn (they are always vcc and gnd; the test checks that in the netlist).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import schemdraw  # noqa: E402
import schemdraw.elements as elm  # noqa: E402

from pedal_agent.build import load_block, parse_value, render, taper  # noqa: E402

ORANGE_LIGHT = "#fde9df"            # same as the dashboard's component list (dashboard/app.py)
STAGE_COLOR = "#8a8a84"
KINDS = "RCDQX"
GRID = 0.001                        # coordinates are rounded to this ...
TOL = 0.02                          # ... and points closer than this are the same point (invisible gap)

OPAMP_PINS = ("inp", "inn", "vcc", "vee", "out")         # pin order of the op-amp wrappers in models/

# Part names shown on the drawings (the BOM keeps the SPICE model names; models/README.md has the sources)
PART_NAME = {"D1N914": "1N914", "DLED_RED": "red LED", "DGE": "Ge diode (1N34A stand-in)",
             "Q2N4401": "2N4401", "Q2N3904": "2N3904", "QBC549C": "BC549C",
             "JRC4558_HALF": "JRC4558 (1/2)", "LM741": "LM741"}

# What knob position 1 means, per pot (drawing text only; block.yaml, which the Planner reads, is unchanged)
POT_DIRECTION = {("od_ts808", "drive"): "1 = max drive", ("od_ts808", "tone"): "1 = brightest",
                 ("od_ts808", "level"): "1 = loudest", ("dist_distplus", "gain"): "1 = max gain",
                 ("dist_distplus", "level"): "1 = loudest",
                 ("fuzz_ff_si", "fuzz"): "1 = wiper at Q2 emitter, max fuzz",
                 ("fuzz_ff_si", "volume"): "1 = loudest"}

# Pot ends as seen on the page, by drawing direction: (end at the element start, end at the element end)
POT_ENDS = {"down": ("top", "bottom"), "up": ("bottom", "top"), "right": ("left", "right"), "left": ("right", "left")}


def value_text(v: str) -> str:
    """'4.7e-08' -> '47n', '1.5Meg' -> '1.5M', '204130' -> '204k'."""
    x = parse_value(v)
    for suf, f in (("M", 1e6), ("k", 1e3), ("", 1.0), ("m", 1e-3), ("u", 1e-6), ("n", 1e-9), ("p", 1e-12)):
        if abs(x) >= f * 0.9995:
            return f"{x / f:.3g}{suf}"
    return f"{x:.3g}"


def parse_subckt(text: str) -> dict[str, list[str]]:
    """Element lines of a rendered block: designator -> tokens (comments stripped)."""
    parts = {}
    for line in text.splitlines():
        line = line.split(";")[0].strip()
        if line and line[0] in KINDS:
            tok = line.split()
            parts[tok[0]] = tok
    return parts


def netlist_terminals(tok: list[str]) -> dict[str, str]:
    """Terminal -> node of a netlist element (names as used by Sketch parts)."""
    d = tok[0][0]
    if d in "RC":
        return {"1": tok[1], "2": tok[2]}
    if d == "D":
        return {"anode": tok[1], "cathode": tok[2]}
    if d == "Q":
        return {"collector": tok[1], "base": tok[2], "emitter": tok[3]}
    return dict(zip(OPAMP_PINS, tok[1:6]))


def _key(p) -> tuple[float, float]:
    return (round(p[0] / GRID) * GRID, round(p[1] / GRID) * GRID)


@dataclass
class Placed:
    designator: str                     # netlist designator (pot halves: R20A, R20B)
    terminals: dict[str, tuple]         # terminal name -> point
    symmetric: bool                     # R/C: terminals 1 and 2 may be swapped


@dataclass
class Sketch:
    """A block schematic being drawn: schemdraw elements plus the bookkeeping for the connectivity check."""
    block_id: str
    params: dict = field(default_factory=dict)
    unit: float = 2.0

    def __post_init__(self):
        self.meta = load_block(self.block_id)[1]
        self.vals = {k: p.get("default", p.get("value")) for k, p in self.meta["params"].items()} | self.params
        self.netlist = render(self.block_id, self.params)
        self.parts = parse_subckt(self.netlist)
        self.adjustable = self._adjustable()
        self.d = schemdraw.Drawing(show=False, canvas="matplotlib")
        self.d.config(unit=self.unit, fontsize=9, lw=1.1)
        self.placed: list[Placed] = []
        self.wires: list[tuple[tuple, tuple]] = []
        self.tags: list[tuple[str, tuple]] = []
        self.drawn: set[str] = set()
        self.elements: dict[str, schemdraw.elements.Element] = {}
        self.labels: dict[str, str] = {}             # text drawn next to each part (for tests)

    # ---------- what the block says ----------
    def _adjustable(self) -> set[str]:
        """Designators the agent can change: pots, component params, parts selected by a choice."""
        out = set()
        for name, p in self.meta["params"].items():
            if p["type"] == "pot":
                out.add(p["designator"])
            elif p["type"] == "component":
                out.add(name)
            elif p["type"] == "choice":
                out.update(p["designators"])
        return out

    def has(self, des: str) -> bool:
        return des in self.parts or f"{des}A" in self.parts

    def pot(self, des: str) -> tuple[str, dict]:
        return next((n, p) for n, p in self.meta["params"].items() if p["type"] == "pot" and p["designator"] == des)

    # ---------- labels ----------
    def model_name(self, des: str) -> str:
        tok = self.parts[des]
        model = tok[3] if des[0] == "D" else tok[4] if des[0] == "Q" else tok[-1]
        return PART_NAME.get(model, model)

    def label_of(self, des: str) -> str:
        if des[0] in "RC":
            if self._is_pot(des):
                return self.pot_label(des)
            return f"{des}\n{value_text(self.parts[des][3])}"
        return f"{des}\n{self.model_name(des)}"

    def pot_label(self, des: str, direction: str | None = None, a_end: str = "start") -> str:
        """Rheostat: 'R19 500k log / drive 0.90 (1 = max drive) / set to 320k'. Divider: the two segments named by
        their ends on the page, in page order (upper / left first), e.g. 'top-wiper 30k' over 'wiper-bottom 70k'."""
        name, p = self.pot(des)
        x = float(self.vals[name])
        f = taper(1.0 - x if p.get("invert") else x, p["taper"])
        rt = parse_value(p["r_total"])
        note = f"({POT_DIRECTION.get((self.block_id, name), '0 to 1')})"
        head = (f"{des} {value_text(p['r_total'])} {'log' if p['taper'] == 'log' else 'linear'}\n"
                f"{name} {x:.2f}" + ("\n" if len(note) > 18 else " ") + note)
        if p["mode"] == "rheostat":
            return f"{head}\nset to {value_text(str(rt * f))}"
        seg_a, seg_b = rt * f, rt * (1 - f)                  # A: a_end .. wiper, B: wiper .. other end
        first, second = POT_ENDS[direction or "down"]
        at_start, at_end = (seg_a, seg_b) if a_end == "start" else (seg_b, seg_a)
        if direction in ("up", "left"):                       # page order: upper / left segment first
            first, second, at_start, at_end = second, first, at_end, at_start
        s1 = f"{first}-wiper {value_text(str(at_start))}"
        s2 = f"wiper-{second} {value_text(str(at_end))}"
        return f"{head}\n{s1}\n{s2}" if direction in ("up", "down", None) else f"{head}\n{s1} / {s2}"

    # ---------- placing ----------
    def _text(self, des: str, text: str) -> str:
        self.labels[des] = text
        return text

    def _add(self, des: str, e, terminals: dict[str, tuple], symmetric=False, halves=None):
        if des in self.drawn:
            raise ValueError(f"{des} drawn twice")
        self.drawn.add(des)
        self.d.add(e)
        self.elements[des] = e
        if des in self.adjustable:
            hl = elm.EncircleBox([e], padx=0.12, pady=0.12, includelabels=False, cornerradius=0.15)
            self.d.add(hl.fill(ORANGE_LIGHT).color(ORANGE_LIGHT).zorder(0.5))
        for name, anchors in (halves or {des: terminals}).items():
            self.placed.append(Placed(name, {t: _key(e.absanchors[a]) for t, a in anchors.items()}, symmetric))
        return e

    def two(self, des: str, start, direction: str, length: float | None = None, side: str | None = None):
        """R, C or D from start in direction ('right', 'left', 'up', 'down'); label on side ('above', 'below',
        'left', 'right'; default above / right). A diode's anode is its start: draw it in its netlist direction."""
        if des not in self.parts:
            raise KeyError(f"{des} is not in the rendered netlist of {self.block_id}")
        k = des[0]
        if k == "R":
            e = elm.ResistorVar() if self._is_pot(des) else elm.Resistor()
        elif k == "C":
            e = elm.Capacitor()
        else:
            e = elm.LED() if "LED" in self.parts[des][3].upper() else elm.Diode()
        e = getattr(e.at(_pt(start)), direction)()
        if length is not None:
            e = e.length(length)
        e = e.label(self._text(des, self.label_of(des)), loc=_loc(direction, side), fontsize=8)
        if k == "D":
            return self._add(des, e, {"anode": "start", "cathode": "end"})
        return self._add(des, e, {"1": "start", "2": "end"}, symmetric=True)

    def _is_pot(self, des: str) -> bool:
        return any(p["type"] == "pot" and p["designator"] == des for p in self.meta["params"].values())

    def divider(self, des: str, start, direction: str, a_end: str = "start", side: str | None = None,
                flip: bool = False, length: float | None = None):
        """Pot drawn whole; netlist halves desA (a_end .. wiper) and desB (wiper .. other end).
        flip moves the wiper to the other side."""
        e = getattr(elm.Potentiometer().at(_pt(start)), direction)()
        if length is not None:
            e = e.length(length)
        if flip:
            e = e.flip()
        e = e.label(self._text(des, self.pot_label(des, direction, a_end)), loc=_loc(direction, side), fontsize=8)
        b_end = "end" if a_end == "start" else "start"
        return self._add(des, e, {}, halves={f"{des}A": {"1": a_end, "2": "tap"}, f"{des}B": {"1": "tap", "2": b_end}},
                         symmetric=True)

    def bjt(self, des: str, base_at, loc: str = "right"):
        e = elm.BjtNpn(circle=True).right().anchor("base").at(_pt(base_at))
        e = e.label(self._text(des, self.label_of(des)), loc=loc, fontsize=8)
        return self._add(des, e, {"collector": "collector", "base": "base", "emitter": "emitter"})

    def opamp(self, des: str, at, anchor: str = "in2"):
        """in1 = inverting (-, top), in2 = non-inverting (+, bottom)."""
        e = elm.Opamp(leads=True).right().anchor(anchor).at(_pt(at))
        e = e.label(des, loc="center", fontsize=8, ofst=(-0.3, 0)).label(self._text(des, self.model_name(des)), loc="bottom",
                                                                        fontsize=7, ofst=(0, -0.1))
        return self._add(des, e, {"inp": "in2", "inn": "in1", "out": "out"})

    # ---------- wires and tags ----------
    def wire(self, *points):
        pts = [_pt(p) for p in points]
        for a, b in zip(pts, pts[1:]):
            self.d.add(elm.Line().at(a).to(b))
            self.wires.append((_key(a), _key(b)))
        return pts[-1]

    def gnd(self, at):
        self.tags.append(("gnd", _key(_pt(at))))
        return self.d.add(elm.Ground().at(_pt(at)))

    def vcc(self, at):
        self.tags.append(("vcc", _key(_pt(at))))
        return self.d.add(elm.Vdd().at(_pt(at)).label("+9V", fontsize=8))

    def vr(self, at, direction: str = "up"):
        """Bias reference Vr = Vcc/2, drawn as a rail symbol (bar above for up, below for down)."""
        e = elm.Vdd() if direction == "up" else elm.Vss()
        self.tags.append(("vr", _key(_pt(at))))
        return self.d.add(e.at(_pt(at)).label("Vr", fontsize=8))

    def port(self, name: str, at, loc: str = "left"):
        self.d.add(elm.Dot(open=True).at(_pt(at)).label(name, loc=loc, fontsize=9))
        self.tags.append((name, _key(_pt(at))))

    def bias(self, upper: str, lower: str, cap: str, at=(0.0, 0.0)):
        """Vr = Vcc/2 divider (upper, lower) with its filter cap, as its own stage; at = ground level, left."""
        x, y = at
        v = self.vcc((x, y + 4))
        self.two(upper, (x, y + 4), "down", side="left")
        self.two(lower, (x, y + 2), "down", side="left")
        self.gnd((x, y))
        self.wire((x, y + 2), (x + 1.6, y + 2))
        self.two(cap, (x + 1.6, y + 2), "down")
        self.gnd((x + 1.6, y))
        self.wire((x + 1.6, y + 2), (x + 2.8, y + 2))
        self.vr((x + 2.8, y + 2))
        self.stage("Bias: Vr = Vcc/2", [upper, lower, cap], extra=[v])

    def stage(self, title: str, designators: list[str], extra=(), padx: float = 0.4, pady: float = 0.4):
        """Dashed box around a stage's parts (and extra elements, e.g. its supply symbols)."""
        els = [self.elements[x] for x in designators if x in self.elements] + list(extra)
        box = elm.EncircleBox(els, padx=padx, pady=pady, cornerradius=0.25)
        self.d.add(box.linestyle("--").color(STAGE_COLOR).linewidth(0.8).zorder(0.4)
                   .label(title, loc="top", fontsize=9, color=STAGE_COLOR))

    # ---------- connectivity (from geometry) ----------
    def _snapped(self):
        """Terminals, tags and wires with points closer than TOL replaced by one representative point."""
        pts = sorted({p for pl in self.placed for p in pl.terminals.values()} | {p for _, p in self.tags}
                     | {p for w in self.wires for p in w})
        rep: dict[tuple, tuple] = {}
        for i, a in enumerate(pts):
            if a in rep:
                continue
            rep[a] = a
            for b in pts[i + 1:]:
                if b[0] - a[0] > TOL:
                    break
                if abs(b[1] - a[1]) <= TOL:
                    rep.setdefault(b, a)
        terms = [(pl, {t: rep[p] for t, p in pl.terminals.items()}) for pl in self.placed]
        tags = [(name, rep[p]) for name, p in self.tags]
        wires = [(rep[a], rep[b]) for a, b in self.wires if rep[a] != rep[b]]
        return rep, terms, tags, wires

    def connections(self) -> tuple[dict[tuple, int], dict[str, int]]:
        """Union-find over points. Returns (point -> net id, tag name -> net id); keys are the original points."""
        rep, terms, tags, wires = self._snapped()
        parent = {p: p for p in set(rep.values())}

        def find(p):
            while parent[p] != p:
                parent[p] = parent[parent[p]]
                p = parent[p]
            return p

        for a, b in wires:
            parent[find(a)] = find(b)
            for p in parent:
                if p not in (a, b) and _on_segment(p, a, b):
                    parent[find(p)] = find(a)
        by_name: dict[str, tuple] = {}
        for name, p in tags:
            if name in by_name:
                parent[find(p)] = find(by_name[name])
            by_name[name] = p
        ids: dict[tuple, int] = {}
        net = {p: ids.setdefault(find(r), len(ids)) for p, r in rep.items()}
        return net, {name: net[p] for name, p in by_name.items()}

    def junctions(self) -> list[tuple]:
        """Points where three or more connections meet (drawn as dots)."""
        _, terms, _, wires = self._snapped()
        count: dict[tuple, int] = {}
        for a, b in wires:
            count[a] = count.get(a, 0) + 1
            count[b] = count.get(b, 0) + 1
        for _, t in terms:
            for p in set(t.values()):
                count[p] = count.get(p, 0) + 1
        for a, b in wires:                          # wire ends or terminals landing mid-wire
            for p in list(count):
                if p not in (a, b) and _on_segment(p, a, b):
                    count[p] += 2
        return [p for p, c in count.items() if c >= 3]

    # ---------- output ----------
    def finish(self, caption: str):
        for p in self.junctions():
            self.d.add(elm.Dot(radius=0.09).at(p))
        x0, y0, x1, y1 = self.d.get_bbox()
        self.d.add(elm.Label().at((x0, y0 - 0.5)).label(caption, halign="left", valign="top", fontsize=8,
                                                       color="#55554f"))
        return self

    def save(self, path: str | Path, dpi: int = 150) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.d.save(str(path), transparent=False, dpi=dpi)
        return path


def _loc(direction: str, side: str | None) -> str:
    """schemdraw label loc for a side of the page, given the element direction."""
    side = side or ("above" if direction in ("right", "left") else "right")
    table = {"right": {"above": "top", "below": "bottom"}, "left": {"above": "top", "below": "bottom"},
             "down": {"left": "top", "right": "bottom"}, "up": {"right": "bottom", "left": "top"}}
    return table[direction][side]


def _pt(p):
    return (float(p[0]), float(p[1]))


def _on_segment(p, a, b) -> bool:
    (px, py), (ax, ay), (bx, by) = p, a, b
    length = max(((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5, 1e-9)
    if abs((bx - ax) * (py - ay) - (by - ay) * (px - ax)) / length > TOL:   # distance from the line
        return False
    return min(ax, bx) - TOL <= px <= max(ax, bx) + TOL and min(ay, by) - TOL <= py <= max(ay, by) + TOL


def caption(sk: Sketch) -> str:
    src = sk.meta["source"]["schematic"]
    def shown(k):
        p, v = sk.meta["params"][k], sk.vals[k]
        return value_text(str(v)) if p["type"] == "component" else PART_NAME.get(v, v) if p["type"] == "choice" else v

    settings = ", ".join(f"{k} {shown(k)}" for k in sk.meta["params"])
    m = re.match(r"(GGG [^,]*?) schematic", src)
    return (f"Based on the {m.group(1) if m else src} schematic, redrawn; values as simulated ({settings}).\n"
            "Shaded: parts the agent can change."
            + (" Op-amp supply pins (+9V, ground) not drawn." if any(d[0] == "X" for d in sk.parts) else ""))


def check_drawing(sk: Sketch) -> list[str]:
    """Problems found comparing the drawing with the rendered netlist (empty list = they match):
    every netlist part drawn once and nothing else, and the drawn connections equal the netlist nodes
    (one drawn net per node and the reverse; tags gnd/vcc/vr/in/out on the node of that name)."""
    problems = []
    drawn = {pl.designator for pl in sk.placed}
    if missing := sorted(set(sk.parts) - drawn):
        problems.append(f"not drawn: {missing}")
    if extra := sorted(drawn - set(sk.parts)):
        problems.append(f"drawn but not in the netlist: {extra}")
    net, tag_net = sk.connections()
    f: dict[int, str] = {}                              # drawn net -> netlist node

    def bind(n: int, node: str, why: str):
        if f.setdefault(n, node) != node:
            problems.append(f"{why}: drawn net joins nodes {f[n]} and {node}")

    for name, n in tag_net.items():
        bind(n, name, f"tag {name}")
    sym = []
    for pl in sk.placed:
        if pl.designator not in sk.parts:
            continue
        nodes = netlist_terminals(sk.parts[pl.designator])
        if pl.symmetric:
            sym.append((pl, (net[pl.terminals["1"]], net[pl.terminals["2"]]), (nodes["1"], nodes["2"])))
            continue
        for t, p in pl.terminals.items():
            bind(net[p], nodes[t], f"{pl.designator}.{t}")
        for t in set(nodes) - set(pl.terminals):        # op-amp supply pins, not drawn
            if nodes[t] != {"vcc": "vcc", "vee": "gnd"}[t]:
                problems.append(f"{pl.designator}.{t} is {nodes[t]}, drawn as implied {t}")
    todo = sym
    while todo:                                         # two-terminal parts: orientation free, follow known ends
        left = []
        for pl, (a, b), (x, y) in todo:
            if a in f or b in f:
                if f.get(a) == x or f.get(b) == y:
                    bind(a, x, pl.designator)
                    bind(b, y, pl.designator)
                elif f.get(a) == y or f.get(b) == x:
                    bind(a, y, pl.designator)
                    bind(b, x, pl.designator)
                else:
                    problems.append(f"{pl.designator}: drawn between {f.get(a)} and {f.get(b)}, netlist {x}-{y}")
            else:
                left.append((pl, (a, b), (x, y)))
        if len(left) == len(todo):
            problems.append(f"cannot place {[pl.designator for pl, *_ in left]} (not connected to anything known)")
            break
        todo = left
    used = {n for pl in sk.placed for n in (net[p] for p in pl.terminals.values())} | set(tag_net.values())
    if unbound := used - set(f):
        problems.append(f"{len(unbound)} drawn net(s) not matched to a node")
    inverse: dict[str, set[int]] = {}
    for n, node in f.items():
        inverse.setdefault(node, set()).add(n)
    for node, ns in inverse.items():
        if len(ns) > 1:
            problems.append(f"node {node} is drawn as {len(ns)} separate nets")
    all_nodes = {v for tok in sk.parts.values() for v in netlist_terminals(tok).values()}
    if lost := sorted(all_nodes - set(inverse) - {"vcc", "gnd"}):
        problems.append(f"nodes not drawn: {lost}")
    return problems
