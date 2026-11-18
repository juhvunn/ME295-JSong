"""Common test harness: guitar pickup model -> block chain -> amp input load."""
# Typical passive single-coil pickup (order of magnitude) and cable.
PICKUP = {"R": "6k", "L": "2.5", "C_cable": "470p"}
LOAD = "1Meg"
VCC = 9.0

def chain_nodes(n):
    """Signal nodes for an n-block chain: in -> n1 -> ... -> out."""
    return ["in"] + [f"n{i}" for i in range(1, n)] + ["out"]

def netlist(blocks, models_text, amp, f0, control, source=None):
    """blocks: [(subckt_text, subckt_name), ...] in signal order; instance i is X<i+1>.
    models_text is pasted in (no .include: the simulate() filter rejects it).
    source: replaces the sine source driving node emf (audio renders: the clip source); default = the test sine."""
    p = PICKUP
    source = source or f"Vsrc emf 0 dc 0 ac 1 sin(0 {amp} {f0})"
    nodes = chain_nodes(len(blocks))
    subckts = "\n".join(text for text, _ in blocks)
    instances = "\n".join(f"X{i + 1} {nodes[i]} {nodes[i + 1]} vcc 0 {name}"
                          for i, (_, name) in enumerate(blocks))
    return f"""* harness: {' -> '.join(name for _, name in blocks)}
{models_text}
{subckts}
Vcc vcc 0 {VCC}
{source}
Rpu emf pu1 {p['R']}
Lpu pu1 in {p['L']}
Ccab in 0 {p['C_cable']}
{instances}
Rload out 0 {LOAD}
.control
{control}
.endc
.end
"""
