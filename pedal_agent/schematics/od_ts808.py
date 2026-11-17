"""od_ts808 schematic: bias, input buffer, clipping amplifier, tone and level, output buffer (left to right)."""
from pedal_agent.schematics.common import Sketch


def xy(e, anchor):
    p = e.absanchors[anchor]
    return (p[0], p[1])


def draw(s: Sketch) -> None:
    # --- bias reference Vr = Vcc/2 ---
    v = s.vcc((0, 4))
    s.two("R9", (0, 4), "down", side="left")
    s.two("R10", (0, 2), "down", side="left")
    s.gnd((0, 0))
    s.wire((0, 2), (1.6, 2))
    s.two("C7", (1.6, 2), "down")
    s.gnd((1.6, 0))
    s.wire((1.6, 2), (2.8, 2))
    s.vr((2.8, 2))
    s.stage("Bias: Vr = Vcc/2", ["R9", "R10", "C7"], extra=[v])

    # --- input buffer (Q1 emitter follower) ---
    s.port("in", (5, 0))
    s.wire((5, 0), (6, 0))
    s.two("R22", (6, 0), "down", side="left")
    s.gnd((6, -2))
    s.two("C1", (6, 0), "right")
    s.two("R1", (8, 0), "right")
    s.two("R2", (10, 0), "down", side="left")
    s.vr((10, -2), "down")
    s.wire((10, 0), (11, 0))
    q1 = s.bjt("Q1", (11, 0))
    c, e = xy(q1, "collector"), xy(q1, "emitter")
    s.wire(c, (c[0], c[1] + 0.6))
    v1_ = s.vcc((c[0], c[1] + 0.6))
    e1 = (e[0], -1.6)
    s.wire(e, e1)
    s.two("R3", e1, "down", side="left")
    s.gnd((e1[0], e1[1] - 2))
    s.two("C2", e1, "right")
    p1 = (e1[0] + 2.4, e1[1])
    s.wire((e1[0] + 2, e1[1]), p1)
    s.two("R5", p1, "down")
    s.vr((p1[0], p1[1] - 2), "down")
    s.stage("Input buffer", ["R22", "C1", "R1", "R2", "Q1", "R3", "C2", "R5"], extra=[v1_])

    # --- clipping amplifier (IC1a): feedback network above, C3 + R6 from the - input to Vr ---
    a = s.opamp("X1A", (p1[0] + 6.5, p1[1]))
    s.wire(p1, xy(a, "in2"))
    m1, o1 = xy(a, "in1"), xy(a, "out")
    mx, rx = m1[0] - 0.7, o1[0] + 0.7
    top = m1[1] + 9.0
    s.wire(m1, (mx, m1[1]), (mx, top))
    s.wire(o1, (rx, o1[1]), (rx, top))
    y = m1[1] + 1.6
    s.two("C3", (mx, y), "left")
    s.two("R6", (mx - 2, y), "left")
    s.vr((mx - 4, y), "down")
    mid = (mx + rx) / 2

    def branch(des, y, reverse=False, side="above"):    # one part between the m1 and o1 columns
        s.wire((mx, y), (mid - 1, y))
        if reverse:                                 # anode on the o1 side
            s.two(des, (mid + 1, y), "left", side=side)
        else:
            s.two(des, (mid - 1, y), "right", side=side)
        s.wire((mid + 1, y), (rx, y))

    branch("C4", m1[1] + 3.2)
    for an, ca in (("D1", "D2"), ("D3", "D4")):     # si pair or LED pair; none for D_clip = none
        if s.has(an):                               # labels outside the pair (LED arrows point inwards)
            branch(an, m1[1] + 5.0, side="below")   # D1: anode m1 -> cathode o1
            branch(ca, m1[1] + 7.2, reverse=True)   # D2: anode o1 -> cathode m1
    s.two("R7", (mx, top), "right")
    s.two("R19", (mx + 2, top), "right")
    s.wire((mx + 4, top), (rx, top))
    s.stage("Clipping amplifier", ["X1A", "C3", "R6", "C4", "D1", "D2", "D3", "D4", "R7", "R19"])

    # --- tone (passive LPF + IC1b with the tone pot) and level ---
    s.wire((rx, o1[1]), (rx + 1.2, o1[1]))
    s.two("R8", (rx + 1.2, o1[1]), "right")
    t1 = (rx + 3.2, o1[1])
    s.two("C5", t1, "down", side="left")
    s.gnd((t1[0], t1[1] - 2))
    r16 = (t1[0] + 1.6, t1[1])
    s.wire(t1, r16)
    s.two("R16", r16, "down")
    s.vr((r16[0], r16[1] - 2), "down")
    ptop = t1[1] + 7.0
    s.wire(t1, (t1[0], ptop))
    pot = s.divider("R20", (t1[0], ptop), "right", a_end="start", flip=True, length=3, side="above")
    tap = xy(pot, "tap")
    s.two("C9", tap, "down", side="right")
    s.two("R11", (tap[0], tap[1] - 2), "down", side="right")
    s.gnd((tap[0], tap[1] - 4))
    b = s.opamp("X1B", (t1[0] + 5.2, t1[1]))
    s.wire(r16, xy(b, "in2"))
    m2, o2 = xy(b, "in1"), xy(b, "out")
    mx2, rx2 = m2[0] - 0.7, o2[0] + 0.7
    s.wire(xy(pot, "end"), (mx2, ptop))
    s.wire(m2, (mx2, m2[1]), (mx2, ptop + 1.4))
    s.two("R17", (mx2, ptop + 1.4), "right", length=rx2 - mx2)
    s.wire((rx2, ptop + 1.4), (rx2, o2[1]), o2)
    s.two("C8", (rx2, o2[1]), "right")
    s.two("R18", (rx2 + 2, o2[1]), "right")
    v1 = (rx2 + 4.4, o2[1])
    s.wire((rx2 + 4, o2[1]), v1)
    lvl = s.divider("R21", v1, "down", a_end="end", length=3, side="left")
    s.vr(xy(lvl, "end"), "down")
    s.stage("Tone and level", ["R8", "C5", "R16", "R20", "C9", "R11", "X1B", "R17", "C8", "R18", "R21"])

    # --- output buffer (Q2 emitter follower) ---
    w2 = xy(lvl, "tap")
    s.wire(w2, (w2[0] + 1.2, w2[1]))
    s.two("C10", (w2[0] + 1.2, w2[1]), "right")
    b2 = (w2[0] + 3.6, w2[1])
    s.wire((w2[0] + 3.2, w2[1]), b2)
    s.two("R12", b2, "down", side="left")
    s.vr((b2[0], b2[1] - 2), "down")
    s.wire(b2, (b2[0] + 1, b2[1]))
    q2 = s.bjt("Q2", (b2[0] + 1, b2[1]))
    c, e = xy(q2, "collector"), xy(q2, "emitter")
    s.wire(c, (c[0], c[1] + 0.6))
    v2 = s.vcc((c[0], c[1] + 0.6))
    e2 = (e[0], e[1] - 0.8)
    s.wire(e, e2)
    s.two("R14", e2, "down", side="left")
    s.gnd((e2[0], e2[1] - 2))
    s.two("R15", e2, "right")
    s.two("C11", (e2[0] + 2, e2[1]), "right")
    out = (e2[0] + 4.6, e2[1])
    s.wire((e2[0] + 4, e2[1]), out)
    s.two("R13", out, "down")
    s.gnd((out[0], out[1] - 2))
    s.wire(out, (out[0] + 1, out[1]))
    s.port("out", (out[0] + 1, out[1]), loc="right")
    s.stage("Output buffer", ["C10", "R12", "Q2", "R14", "R15", "C11", "R13"], extra=[v2])
