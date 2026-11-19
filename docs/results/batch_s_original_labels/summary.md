# Benchmark v1: summary

2062 finished runs from `runs\bench\v1`; methods: agent, baseline_fixed_topology, random_catalog, random_fixed_topology, random_fixed_topology_oracle; budget 12 sims. Success = all metrics in range (stop_reason all_pass). The oracle is not run on D or hand targets. Infrastructure errors left out (re-run): 0.

Random-method knob range: random catalog: restricted knob range (0.05-0.95); random fixed-topo: restricted knob range (0.05-0.95); oracle: restricted knob range (0.05-0.95)

Code commits per method (runs): agent: b0044e10d8 ×51; agent fixed-topo: b0044e10d8 ×51; random catalog: not recorded ×720; random fixed-topo: not recorded ×720; oracle: not recorded ×520

## Full set

Success rate (successful runs / runs, 95 % Wilson interval).

| Group | agent | agent fixed-topo | random catalog | random fixed-topo | oracle |
|---|---|---|---|---|---|
| A | 100 % (6/6) [61–100] | 100 % (6/6) [61–100] | 31 % (44/140) [24–40] | 58 % (81/140) [50–66] | 58 % (81/140) [50–66] |
| B | 95 % (19/20) [76–99] | 85 % (17/20) [64–95] | 22 % (40/180) [17–29] | 2 % (3/180) [1–5] | 58 % (104/180) [50–65] |
| C | 30 % (6/20) [15–52] | 25 % (5/20) [11–47] | 7 % (14/200) [4–11] | 0 % (0/200) [0–2] | 66 % (131/200) [59–72] |
| D | 0 % (0/2) [0–66] | 0 % (0/2) [0–66] | 0 % (0/80) [0–5] | 0 % (0/80) [0–5] | – |
| Hand | 100 % (3/3) [44–100] | 100 % (3/3) [44–100] | 31 % (37/120) [23–40] | 21 % (25/120) [15–29] | – |
| All | 67 % (34/51) [53–78] | 61 % (31/51) [47–73] | 19 % (135/720) [16–22] | 15 % (109/720) [13–18] | 61 % (316/520) [57–65] |

## Subset view (12 targets: G03, G04, G08, G12, G13, G16, G18, G23, G25, G26, H4, U3); all methods on exactly these targets (random methods filtered from their full-set runs)

Success rate (successful runs / runs, 95 % Wilson interval).

| Group | agent | agent fixed-topo | random catalog | random fixed-topo | oracle |
|---|---|---|---|---|---|
| A | 100 % (6/6) [61–100] | 100 % (6/6) [61–100] | 28 % (11/40) [16–43] | 68 % (27/40) [52–80] | 60 % (24/40) [45–74] |
| B | 95 % (19/20) [76–99] | 85 % (17/20) [64–95] | 21 % (17/80) [14–31] | 0 % (0/80) [0–5] | 70 % (56/80) [59–79] |
| C | 30 % (6/20) [15–52] | 25 % (5/20) [11–47] | 10 % (8/80) [5–19] | 0 % (0/80) [0–5] | 81 % (65/80) [71–88] |
| D | 0 % (0/2) [0–66] | 0 % (0/2) [0–66] | 0 % (0/20) [0–16] | 0 % (0/20) [0–16] | – |
| Hand | 100 % (3/3) [44–100] | 100 % (3/3) [44–100] | 45 % (9/20) [26–66] | 95 % (19/20) [76–99] | – |
| All | 67 % (34/51) [53–78] | 61 % (31/51) [47–73] | 19 % (45/240) [14–24] | 19 % (46/240) [15–25] | 72 % (145/200) [66–78] |

## C split (full set)

C targets split by whether the solution's chain at its default settings already passes (analysis flag from `scripts/flag_defaults.py`).

| C targets | agent | agent fixed-topo | random catalog | random fixed-topo | oracle |
|---|---|---|---|---|---|
| chain at defaults passes (G17, G23, G26) | 0 % (0/10) | 0 % (0/10) | 8 % (5/60) | 0 % (0/60) | 100 % (60/60) |
| needs tuning (G18, G19, G20, G21, G22, G24, G25) | 60 % (6/10) | 50 % (5/10) | 6 % (9/140) | 0 % (0/140) | 51 % (71/140) |

## C split (subset)

C targets split by whether the solution's chain at its default settings already passes (analysis flag from `scripts/flag_defaults.py`).

| C targets | agent | agent fixed-topo | random catalog | random fixed-topo | oracle |
|---|---|---|---|---|---|
| chain at defaults passes (G23, G26) | 0 % (0/10) | 0 % (0/10) | 12 % (5/40) | 0 % (0/40) | 100 % (40/40) |
| needs tuning (G18, G25) | 60 % (6/10) | 50 % (5/10) | 8 % (3/40) | 0 % (0/40) | 62 % (25/40) |

## Block order, full set (2-block chains)

Runs that simulated at least one 2-block chain; of those, runs that tried the same two blocks in both orders. C targets: runs that tried the solution's order vs only the reversed order (solution chain from the analysis file).

| Method | Runs | With a 2-block chain | Both orders of a pair | C runs | C: solution order tried | C: only reversed order tried |
|---|---|---|---|---|---|---|
| agent | 51 | 24 | 1 | 20 | 4 | 8 |
| agent fixed-topo | 51 | 0 | 0 | 20 | 0 | 0 |
| random catalog | 720 | 705 | 194 | 200 | 109 | 61 |
| random fixed-topo | 720 | 0 | 0 | 200 | 0 | 0 |
| oracle | 520 | 300 | 0 | 200 | 200 | 0 |

## Block order, subset (2-block chains)

Runs that simulated at least one 2-block chain; of those, runs that tried the same two blocks in both orders. C targets: runs that tried the solution's order vs only the reversed order (solution chain from the analysis file).

| Method | Runs | With a 2-block chain | Both orders of a pair | C runs | C: solution order tried | C: only reversed order tried |
|---|---|---|---|---|---|---|
| agent | 51 | 24 | 1 | 20 | 4 | 8 |
| agent fixed-topo | 51 | 0 | 0 | 20 | 0 | 0 |
| random catalog | 240 | 238 | 63 | 80 | 40 | 28 |
| random fixed-topo | 240 | 0 | 0 | 80 | 0 | 0 |
| oracle | 200 | 140 | 0 | 80 | 80 | 0 |

## Details (full set)

| Method | Group | Runs | Success | Median sims to success | Median best score | Mean topology changes | Median wall s | Flagged runs | Tokens in/out | API-equivalent cost USD (no per-token billing) |
|---|---|---|---|---|---|---|---|---|---|---|
| agent | A | 6 | 100 % | 2 | 0 | 0.00 | 7.4 | 0 | 29161/2129 | 0.16 |
| agent | B | 20 | 95 % | 7 | 0 | 1.95 | 53.5 | 0 | 646401/77318 | 4.13 |
| agent | C | 20 | 30 % | 4.5 | 0.204 | 3.80 | 127.6 | 0 | 1419399/167878 | 9.04 |
| agent | D | 2 | 0 % | – | 0.199 | 7.00 | 164.4 | 0 | 215770/25919 | 1.38 |
| agent | Hand | 3 | 100 % | 2 | 0 | 0.00 | 6.4 | 0 | 13945/1026 | 0.08 |
| agent | All | 51 | 67 % | 4 | 0 | 2.53 | 57.5 | 0 | 2324676/274270 | 14.78 |
| agent fixed-topo | A | 6 | 100 % | 2 | 0 | 0.00 | 7.0 | 0 | 29423/2186 | 0.16 |
| agent fixed-topo | B | 20 | 85 % | 3 | 0 | 0.00 | 31.1 | 0 | 725395/89549 | 4.69 |
| agent fixed-topo | C | 20 | 25 % | 4 | 0.395 | 0.00 | 110.5 | 0 | 1334306/139279 | 8.12 |
| agent fixed-topo | D | 2 | 0 % | – | 0.175 | 0.00 | 167.8 | 0 | 253603/24500 | 1.50 |
| agent fixed-topo | Hand | 3 | 100 % | 2 | 0 | 0.00 | 7.4 | 0 | 18975/1511 | 0.11 |
| agent fixed-topo | All | 51 | 61 % | 3 | 0 | 0.00 | 39.3 | 0 | 2361702/257025 | 14.59 |
| random catalog | A | 140 | 31 % | 6 | 0.0389 | 7.46 | 5.5 | 0 | 0/0 | 0.00 |
| random catalog | B | 180 | 22 % | 7 | 0.173 | 7.96 | 4.9 | 0 | 0/0 | 0.00 |
| random catalog | C | 200 | 7 % | 7 | 0.464 | 8.63 | 5.0 | 0 | 0/0 | 0.00 |
| random catalog | D | 80 | 0 % | – | 0.8 | 8.90 | 5.0 | 0 | 0/0 | 0.00 |
| random catalog | Hand | 120 | 31 % | 5 | 0.121 | 7.41 | 4.8 | 0 | 0/0 | 0.00 |
| random catalog | All | 720 | 19 % | 6 | 0.297 | 8.06 | 5.0 | 0 | 0/0 | 0.00 |
| random fixed-topo | A | 140 | 58 % | 5 | 0 | 0.00 | 3.4 | 0 | 0/0 | 0.00 |
| random fixed-topo | B | 180 | 2 % | 4 | 0.514 | 0.00 | 4.5 | 0 | 0/0 | 0.00 |
| random fixed-topo | C | 200 | 0 % | – | 0.499 | 0.00 | 4.5 | 0 | 0/0 | 0.00 |
| random fixed-topo | D | 80 | 0 % | – | 0.759 | 0.00 | 4.5 | 0 | 0/0 | 0.00 |
| random fixed-topo | Hand | 120 | 21 % | 5 | 0.474 | 0.00 | 4.4 | 0 | 0/0 | 0.00 |
| random fixed-topo | All | 720 | 15 % | 5 | 0.476 | 0.00 | 4.4 | 0 | 0/0 | 0.00 |
| oracle | A | 140 | 58 % | 6 | 0 | 0.00 | 3.6 | 0 | 0/0 | 0.00 |
| oracle | B | 180 | 58 % | 6 | 0 | 0.00 | 3.6 | 0 | 0/0 | 0.00 |
| oracle | C | 200 | 66 % | 3 | 0 | 0.00 | 2.9 | 0 | 0/0 | 0.00 |
| oracle | All | 520 | 61 % | 5 | 0 | 0.00 | 3.6 | 0 | 0/0 | 0.00 |

## Per target (successes / runs; median sims to success)

Defaults pass = the solution's chain at default settings already passes (analysis flag).

| Target | Cat. | Subset | Defaults pass | agent | agent fixed-topo | random catalog | random fixed-topo | oracle |
|---|---|---|---|---|---|---|---|---|
| G01 | A |  | no | – | – | 8/20 (8) | 3/20 (6) | 11/20 (4) |
| G02 | A |  | no | – | – | 10/20 (7.5) | 15/20 (5) | 15/20 (5) |
| G03 | A | ✓ | no | 3/3 (2) | 3/3 (2) | 8/20 (7) | 17/20 (7) | 14/20 (6) |
| G04 | A | ✓ | no | 3/3 (2) | 3/3 (2) | 3/20 (5) | 10/20 (5) | 10/20 (5) |
| G05 | A |  | no | – | – | 3/20 (4) | 2/20 (5) | 5/20 (6) |
| G06 | A |  | no | – | – | 3/20 (6) | 14/20 (5.5) | 14/20 (5.5) |
| G07 | A |  | no | – | – | 9/20 (4) | 20/20 (3.5) | 12/20 (8) |
| G08 | B | ✓ | no | 4/5 (8) | 5/5 (3) | 1/20 (12) | 0/20 (–) | 12/20 (7) |
| G09 | B |  | no | – | – | 12/20 (7) | 3/20 (4) | 12/20 (4) |
| G10 | B |  | no | – | – | 1/20 (12) | 0/20 (–) | 4/20 (7.5) |
| G11 | B |  | no | – | – | 5/20 (7) | 0/20 (–) | 13/20 (7) |
| G12 | B | ✓ | no | 5/5 (7) | 5/5 (5) | 8/20 (5) | 0/20 (–) | 15/20 (5) |
| G13 | B | ✓ | no | 5/5 (3) | 5/5 (3) | 7/20 (9) | 0/20 (–) | 15/20 (5) |
| G14 | B |  | no | – | – | 5/20 (4) | 0/20 (–) | 13/20 (7) |
| G15 | B |  | no | – | – | 0/20 (–) | 0/20 (–) | 6/20 (10) |
| G16 | B | ✓ | no | 5/5 (5) | 2/5 (9.5) | 1/20 (7) | 0/20 (–) | 14/20 (6) |
| G17 | C |  | yes | – | – | 0/20 (–) | 0/20 (–) | 20/20 (1) |
| G18 | C | ✓ | no | 4/5 (4) | 5/5 (4) | 2/20 (7) | 0/20 (–) | 15/20 (5) |
| G19 | C |  | no | – | – | 2/20 (11) | 0/20 (–) | 8/20 (7.5) |
| G20 | C |  | no | – | – | 3/20 (7) | 0/20 (–) | 13/20 (5) |
| G21 | C |  | no | – | – | 0/20 (–) | 0/20 (–) | 7/20 (5) |
| G22 | C |  | no | – | – | 1/20 (6) | 0/20 (–) | 10/20 (5) |
| G23 | C | ✓ | yes | 0/5 (–) | 0/5 (–) | 3/20 (5) | 0/20 (–) | 20/20 (1) |
| G24 | C |  | no | – | – | 0/20 (–) | 0/20 (–) | 8/20 (5) |
| G25 | C | ✓ | no | 2/5 (12) | 0/5 (–) | 1/20 (3) | 0/20 (–) | 10/20 (7) |
| G26 | C | ✓ | yes | 0/5 (–) | 0/5 (–) | 2/20 (9) | 0/20 (–) | 20/20 (1) |
| U1 | D |  | – | – | – | 0/20 (–) | 0/20 (–) | – |
| U2 | D |  | – | – | – | 0/20 (–) | 0/20 (–) | – |
| U3 | D | ✓ | – | 0/2 (–) | 0/2 (–) | 0/20 (–) | 0/20 (–) | – |
| U4 | D |  | – | – | – | 0/20 (–) | 0/20 (–) | – |
| H1 | A |  | – | – | – | 1/20 (12) | 3/20 (9) | – |
| H2 | A |  | – | – | – | 0/20 (–) | 1/20 (7) | – |
| H3 | A |  | – | – | – | 13/20 (5) | 0/20 (–) | – |
| H4 | A | ✓ | – | 3/3 (2) | 3/3 (2) | 9/20 (6) | 19/20 (3) | – |
| H5 | B |  | – | – | – | 12/20 (3) | 0/20 (–) | – |
| H6 | A |  | – | – | – | 2/20 (7.5) | 2/20 (7) | – |
