"""Ensure the schematic reflects every component in the rendered template."""
from src.tools.build import TEMPLATES_DIR, build_netlist, diode_clipper_parameters
from scripts.draw_schematic import TEMPLATE_NAME, draw_schematic, parse_components


def test_schematic_components_match_rendered_template(tmp_path):
    template = (TEMPLATES_DIR / TEMPLATE_NAME).read_text(encoding="utf-8")
    template_components = parse_components(template)
    netlist = build_netlist(TEMPLATE_NAME, diode_clipper_parameters())
    netlist_components = parse_components(netlist)

    drawn_components = draw_schematic(tmp_path / "diode_clipper.png")

    assert [(component.name, component.nodes) for component in template_components] == [
        (component.name, component.nodes) for component in netlist_components
    ]
    assert [(component.name, component.nodes, component.value) for component in netlist_components] == [
        (component.name, component.nodes, component.value) for component in drawn_components
    ]
    assert (tmp_path / "diode_clipper.png").is_file()
    assert (tmp_path / "diode_clipper.png").stat().st_size > 0
