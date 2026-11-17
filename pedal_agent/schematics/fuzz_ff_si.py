"""fuzz_ff_si schematic: Q1 input stage, Q2 direct-coupled stage, fuzz and volume; R3 feedback (Q2 emitter to
Q1 base) runs underneath, outside the stage boxes because it joins two stages."""
from pedal_agent.schematics.common import Sketch


def xy(e, anchor):
    p = e.absanchors[anchor]
    return (p[0], p[1])


def draw(s: Sketch) -> None:
    # --- Q1: common-emitter input stage ---
    s.port("in", (0, 0))
    s.two("C1", (0, 0), "right")
    b1 = (2.6, 0)
    s.wire((2, 0), b1, (3.6, 0))
    q1 = s.bjt("Q1", (3.6, 0))
    c1, e1 = xy(q1, "collector"), xy(q1, "emitter")
    g1 = (e1[0], e1[1] - 0.4)
    s.wire(e1, g1)
    s.gnd(g1)
    cy = c1[1] + 1.0
    s.wire(c1, (c1[0], cy))
    s.two("R2", (c1[0], cy), "up", length=2.4, side="right")
    v1 = s.vcc((c1[0], cy + 2.4))
    s.stage("Q1", ["C1", "Q1", "R2"], extra=[v1])

    # --- Q2: direct-coupled, collector load R4 + R5 (output taken at their junction) ---
    s.wire((c1[0], cy), (c1[0] + 3.4, cy))
    q2 = s.bjt("Q2", (c1[0] + 3.4, cy))
    c2, e2 = xy(q2, "collector"), xy(q2, "emitter")
    e2n = (e2[0], e2[1] - 0.6)
    s.wire(e2, e2n)
    s.two("R5", c2, "up", side="right")
    na = (c2[0], c2[1] + 2)
    s.two("R4", na, "up", side="right")
    v2 = s.vcc((na[0], na[1] + 2))
    s.stage("Q2", ["Q2", "R5", "R4"], extra=[v2])

    # --- R3: DC/AC feedback from Q2's emitter to Q1's base, below both stages ---
    fy = -3.0
    rx = (b1[0] + e2n[0]) / 2 - 1
    s.wire(b1, (b1[0], fy), (rx, fy))
    s.two("R3", (rx, fy), "right", side="below")
    s.wire((rx + 2, fy), (e2n[0], fy), e2n)

    # --- fuzz (emitter pot, wiper bypassed by C2) and volume (output from the wiper) ---
    px = e2n[0] + 4.6
    s.wire(e2n, (px, e2n[1]))
    fz = s.divider("R6", (px, e2n[1]), "down", a_end="start", length=2.4, side="left")
    s.gnd(xy(fz, "end"))
    w = xy(fz, "tap")
    s.wire(w, (w[0] + 1.0, w[1]))
    s.two("C2", (w[0] + 1.0, w[1]), "down")
    s.gnd((w[0] + 1.0, w[1] - 2))
    vx = px + 3.4
    s.wire(na, (vx - 2.4, na[1]))
    s.two("C3", (vx - 2.4, na[1]), "right", length=2.4)
    vol = s.divider("R10", (vx, na[1]), "down", a_end="end", length=3, side="left")
    s.gnd(xy(vol, "end"))
    t = xy(vol, "tap")
    s.wire(t, (t[0] + 1.2, t[1]))
    s.port("out", (t[0] + 1.2, t[1]), loc="right")
    s.stage("Fuzz and volume", ["R6", "C2", "C3", "R10"])
