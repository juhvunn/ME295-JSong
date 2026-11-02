"""Draw the diode-clipper schematic from its rendered SPICE netlist."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import schemdraw
import schemdraw.elements as elm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import REPO_ROOT  # noqa: E402
from src.tools.build import build_netlist, diode_clipper_parameters  # noqa: E402

TEMPLATE_NAME = "diode_clipper.cir"


@dataclass(frozen=True)
class Component:
    name: str
    nodes: tuple[str, str]
    value: str
    kind: str


def parse_components(netlist: str) -> list[Component]:
    """Parse the two-terminal components used by the diode-clipper template."""
    components = []
    in_control = False
    for raw_line in netlist.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("*"):
            continue
        if line.lower() == ".control":
            in_control = True
            continue
        if in_control:
            if line.lower() == ".endc":
                in_control = False
            continue
        if line.startswith(".") or line.startswith("+"):
            continue

        fields = line.split()
        kind = fields[0][0].upper()
        if kind not in {"V", "R", "C", "D"}:
            raise ValueError(f"unsupported component in diode-clipper template: {fields[0]}")
        if len(fields) < 4:
            raise ValueError(f"malformed component line: {line}")
        components.append(Component(
            name=fields[0],
            nodes=(fields[1], fields[2]),
            value=" ".join(fields[3:]),
            kind=kind,
        ))
    return components


def _element_for(component: Component, start: tuple[float, float], end: tuple[float, float]):
    element_type = {
        "V": elm.SourceV,
        "R": elm.Resistor,
        "C": elm.Capacitor,
        "D": elm.Diode,
    }[component.kind]
    label = f"{component.name}\n{component.value}"
    location = "left" if component.kind == "V" else "right" if component.kind in {"C", "D"} else "top"
    return element_type().at(start).to(end).label(label, loc=location)


def draw_schematic(output_path: str | Path | None = None) -> list[Component]:
    """Save the rendered diode-clipper schematic and return its components."""
    netlist = build_netlist(TEMPLATE_NAME, diode_clipper_parameters())
    components = parse_components(netlist)

    ground = "0"
    sources = [component for component in components if component.kind == "V"]
    if len(sources) != 1 or ground not in sources[0].nodes:
        raise ValueError("diode-clipper schematic requires one grounded voltage source")
    source = sources[0]
    input_node = next(node for node in source.nodes if node != ground)
    resistors = [component for component in components
                 if component.kind == "R" and input_node in component.nodes]
    if len(resistors) != 1:
        raise ValueError("diode-clipper schematic requires one series resistor")
    resistor = resistors[0]
    output_node = next(node for node in resistor.nodes if node != input_node)
    shunts = [component for component in components if component not in {source, resistor}]
    if any(set(component.nodes) != {output_node, ground} for component in shunts):
        raise ValueError("all clipper shunt components must connect output to ground")

    branch_x = [4.0 + 1.7 * index for index in range(len(shunts))]
    far_x = branch_x[-1]
    node_positions = {
        ground: (0.0, 0.0),
        input_node: (0.0, 2.5),
        output_node: (3.0, 2.5),
    }
    drawing = schemdraw.Drawing(canvas="matplotlib", show=False)
    drawing += _element_for(source, node_positions[source.nodes[0]], node_positions[source.nodes[1]])
    drawing += elm.Line().at((0.0, 2.5)).to((1.0, 2.5))
    resistor_start = (1.0, 2.5) if resistor.nodes[0] == input_node else (3.0, 2.5)
    resistor_end = (3.0, 2.5) if resistor.nodes[1] == output_node else (1.0, 2.5)
    drawing += _element_for(resistor, resistor_start, resistor_end)
    drawing += elm.Line().at((3.0, 2.5)).to((far_x, 2.5))
    drawing += elm.Line().at((0.0, 0.0)).to((far_x, 0.0))

    for component, x_position in zip(shunts, branch_x):
        drawing += elm.Dot().at((x_position, 2.5))
        drawing += elm.Dot().at((x_position, 0.0))
        node_positions[output_node] = (x_position, 2.5)
        node_positions[ground] = (x_position, 0.0)
        drawing += _element_for(component, node_positions[component.nodes[0]], node_positions[component.nodes[1]])

    drawing += elm.Dot().at((0.0, 2.5)).label(input_node, loc="top")
    drawing += elm.Dot().at((3.0, 2.5)).label(output_node, loc="top")
    drawing += elm.Ground().at((0.0, 0.0)).label(ground, loc="left")

    output_path = Path(output_path) if output_path is not None else (
        REPO_ROOT / "results" / "schematics" / "diode_clipper.png"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    drawing.save(str(output_path), transparent=False, dpi=150)
    return components


if __name__ == "__main__":
    print(draw_schematic())
