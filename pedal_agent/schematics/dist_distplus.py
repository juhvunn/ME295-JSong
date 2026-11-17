"""dist_distplus schematic: input and gain stage, clipping, level (left to right); bias above the clipping."""
from pedal_agent.schematics.common import Sketch


def xy(e, anchor):
    p = e.absanchors[anchor]
    return (p[0], p[1])


def draw(s: Sketch) -> None:
    # --- gain stage: input network, non-inverting IC1, gain leg C4-R6-R7 to ground ---
    s.port("in", (5, 0))
    s.wire((5, 0), (6, 0))
    s.two("R1", (6, 0), "down", side="left")
    s.gnd((6, -2))
    s.wire((6, 0), (7.4, 0))
    s.two("C3", (7.4, 0), "down", side="left")
    s.gnd((7.4, -2))
    s.two("C2", (7.4, 0), "right")
    s.two("R5", (9.4, 0), "right")
    p = (11.8, 0)
    s.wire((11.4, 0), p)
    s.two("R4", p, "down")
    s.vr((p[0], -2), "down")
    a = s.opamp("X1", (p[0] + 8.4, 0))
    s.wire(p, xy(a, "in2"))
    m, o = xy(a, "in1"), xy(a, "out")
    mx, rx = m[0] - 0.7, o[0] + 0.7
    top = m[1] + 5.0
    s.wire(m, (mx, m[1]), (mx, top))
    s.wire(o, (rx, o[1]), (rx, top))
    y = m[1] + 2.0
    s.two("C4", (mx, y), "left")
    s.two("R6", (mx - 2, y), "left")
    s.two("R7", (mx - 4, y), "left")
    s.gnd((mx - 6, y))
    mid = (mx + rx) / 2
    s.wire((mx, m[1] + 3.4), (mid - 1, m[1] + 3.4))
    s.two("C5", (mid - 1, m[1] + 3.4), "right")
    s.wire((mid + 1, m[1] + 3.4), (rx, m[1] + 3.4))
    s.wire((mx, top), (mid - 1, top))
    s.two("R8", (mid - 1, top), "right")
    s.wire((mid + 1, top), (rx, top))
    s.stage("Input and gain stage", ["R1", "C3", "C2", "R5", "R4", "X1", "C4", "R6", "R7", "C5", "R8"])

    # --- hard clipping to ground ---
    s.wire((rx, o[1]), (rx + 1.2, o[1]))
    s.two("C6", (rx + 1.2, o[1]), "right")
    s.two("R9", (rx + 3.2, o[1]), "right")
    c = (rx + 6.0, o[1])
    s.wire((rx + 5.2, o[1]), c)
    x = c[0]
    if s.has("D1"):                                     # D1 anode c -> ground, D2 anode ground -> c
        s.two("D1", c, "down")
        s.gnd((x, c[1] - 2))
        x += 2.4
        s.wire((x - 2.4, c[1]), (x, c[1]))
        s.two("D2", (x, c[1] - 2), "up")
        s.gnd((x, c[1] - 2))
    x += 2.4
    s.wire((x - 2.4, c[1]), (x, c[1]))
    s.two("C7", (x, c[1]), "down")
    s.gnd((x, c[1] - 2))
    s.stage("Clipping", ["C6", "R9", "D1", "D2", "C7"])

    # --- level (output from the wiper, no buffer) ---
    x += 4.6
    s.wire((x - 4.6, c[1]), (x, c[1]))
    lvl = s.divider("R10", (x, c[1]), "down", a_end="end", length=3, side="left")
    s.gnd(xy(lvl, "end"))
    w = xy(lvl, "tap")
    s.wire(w, (w[0] + 1.2, w[1]))
    s.port("out", (w[0] + 1.2, w[1]), loc="right")
    s.stage("Level", ["R10"], padx=0.9)

    s.bias("R2", "R3", "C1", at=(rx + 2.6, o[1] + 3.2))     # in the empty space above the clipping stage
