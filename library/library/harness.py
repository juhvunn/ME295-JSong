"""Common test harness: guitar pickup model -> block -> amp input load."""
# Typical passive single-coil pickup (order of magnitude) and cable.
PICKUP = {"R": "6k", "L": "2.5", "C_cable": "470p"}
LOAD = "1Meg"
VCC = 9.0

def netlist(block_subckt, subckt_name, models_path, amp, f0, control):
    p = PICKUP
    return f"""* harness: {subckt_name}
.include {models_path}
{block_subckt}
Vcc vcc 0 {VCC}
Vsrc emf 0 dc 0 ac 1 sin(0 {amp} {f0})
Rpu emf pu1 {p['R']}
Lpu pu1 in {p['L']}
Ccab in 0 {p['C_cable']}
X1 in out vcc 0 {subckt_name}
Rload out 0 {LOAD}
.control
{control}
.endc
.end
"""
