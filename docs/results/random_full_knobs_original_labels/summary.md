# Benchmark v1: summary

1960 finished runs from `runs\bench\v1_full_knobs`; methods: random_catalog, random_fixed_topology, random_fixed_topology_oracle; budget 12 sims. Success = all metrics in range (stop_reason all_pass). The oracle is not run on D or hand targets. Infrastructure errors left out (re-run): 0.

Random-method knob range: random catalog: full knob range [0, 1] with end stops; random fixed-topo: full knob range [0, 1] with end stops; oracle: full knob range [0, 1] with end stops

Code commits per method (runs): random catalog: 501a876acd (modified) ×720; random fixed-topo: 8b37399d29 ×720; oracle: 8b37399d29 ×520

## Full set

Success rate (successful runs / runs, 95 % Wilson interval).

| Group | random catalog | random fixed-topo | oracle |
|---|---|---|---|
| A | 29 % (40/140) [22–37] | 56 % (79/140) [48–64] | 56 % (78/140) [47–64] |
| B | 17 % (31/180) [12–23] | 7 % (12/180) [4–11] | 49 % (89/180) [42–57] |
| C | 7 % (14/200) [4–11] | 2 % (3/200) [1–4] | 61 % (122/200) [54–67] |
| D | 0 % (0/80) [0–5] | 0 % (0/80) [0–5] | – |
| Hand | 40 % (48/120) [32–49] | 27 % (32/120) [20–35] | – |
| All | 18 % (133/720) [16–21] | 18 % (126/720) [15–20] | 56 % (289/520) [51–60] |

## Subset view (12 targets: G03, G04, G08, G12, G13, G16, G18, G23, G25, G26, H4, U3); all methods on exactly these targets (random methods filtered from their full-set runs)

Success rate (successful runs / runs, 95 % Wilson interval).

| Group | random catalog | random fixed-topo | oracle |
|---|---|---|---|
| A | 40 % (16/40) [26–55] | 52 % (21/40) [37–67] | 52 % (21/40) [37–67] |
| B | 19 % (15/80) [12–29] | 9 % (7/80) [4–17] | 49 % (39/80) [38–60] |
| C | 0 % (0/80) [0–5] | 2 % (2/80) [1–9] | 71 % (57/80) [61–80] |
| D | 0 % (0/20) [0–16] | 0 % (0/20) [0–16] | – |
| Hand | 45 % (9/20) [26–66] | 100 % (20/20) [84–100] | – |
| All | 17 % (40/240) [12–22] | 21 % (50/240) [16–26] | 58 % (117/200) [52–65] |

## C split (full set)

C targets split by whether the solution's chain at its default settings already passes (analysis flag from `scripts/flag_defaults.py`).

| C targets | random catalog | random fixed-topo | oracle |
|---|---|---|---|
| chain at defaults passes (G17, G23, G26) | 2 % (1/60) | 0 % (0/60) | 100 % (60/60) |
| needs tuning (G18, G19, G20, G21, G22, G24, G25) | 9 % (13/140) | 2 % (3/140) | 44 % (62/140) |

## C split (subset)

C targets split by whether the solution's chain at its default settings already passes (analysis flag from `scripts/flag_defaults.py`).

| C targets | random catalog | random fixed-topo | oracle |
|---|---|---|---|
| chain at defaults passes (G23, G26) | 0 % (0/40) | 0 % (0/40) | 100 % (40/40) |
| needs tuning (G18, G25) | 0 % (0/40) | 5 % (2/40) | 42 % (17/40) |

## Block order, full set (2-block chains)

Runs that simulated at least one 2-block chain; of those, runs that tried the same two blocks in both orders. C targets: runs that tried the solution's order vs only the reversed order (solution chain from the analysis file).

| Method | Runs | With a 2-block chain | Both orders of a pair | C runs | C: solution order tried | C: only reversed order tried |
|---|---|---|---|---|---|---|
| random catalog | 720 | 696 | 96 | 200 | 84 | 75 |
| random fixed-topo | 720 | 0 | 0 | 200 | 0 | 0 |
| oracle | 520 | 300 | 0 | 200 | 200 | 0 |

## Block order, subset (2-block chains)

Runs that simulated at least one 2-block chain; of those, runs that tried the same two blocks in both orders. C targets: runs that tried the solution's order vs only the reversed order (solution chain from the analysis file).

| Method | Runs | With a 2-block chain | Both orders of a pair | C runs | C: solution order tried | C: only reversed order tried |
|---|---|---|---|---|---|---|
| random catalog | 240 | 233 | 31 | 80 | 28 | 36 |
| random fixed-topo | 240 | 0 | 0 | 80 | 0 | 0 |
| oracle | 200 | 140 | 0 | 80 | 80 | 0 |

## Details (full set)

| Method | Group | Runs | Success | Median sims to success | Median best score | Mean topology changes | Median wall s | Flagged runs | Tokens in/out | API-equivalent cost USD (no per-token billing) |
|---|---|---|---|---|---|---|---|---|---|---|
| random catalog | A | 140 | 29 % | 6 | 0.101 | 7.77 | 5.2 | 0 | 0/0 | 0.00 |
| random catalog | B | 180 | 17 % | 7 | 0.213 | 8.52 | 5.2 | 0 | 0/0 | 0.00 |
| random catalog | C | 200 | 7 % | 8 | 0.462 | 8.96 | 5.2 | 0 | 0/0 | 0.00 |
| random catalog | D | 80 | 0 % | – | 0.794 | 9.20 | 5.2 | 0 | 0/0 | 0.00 |
| random catalog | Hand | 120 | 40 % | 5.5 | 0.0463 | 7.26 | 4.8 | 0 | 0/0 | 0.00 |
| random catalog | All | 720 | 18 % | 7 | 0.323 | 8.36 | 5.2 | 0 | 0/0 | 0.00 |
| random fixed-topo | A | 140 | 56 % | 5 | 0 | 0.00 | 4.1 | 0 | 0/0 | 0.00 |
| random fixed-topo | B | 180 | 7 % | 6 | 0.362 | 0.00 | 4.7 | 0 | 0/0 | 0.00 |
| random fixed-topo | C | 200 | 2 % | 6 | 0.482 | 0.00 | 4.7 | 0 | 0/0 | 0.00 |
| random fixed-topo | D | 80 | 0 % | – | 0.69 | 0.00 | 4.7 | 0 | 0/0 | 0.00 |
| random fixed-topo | Hand | 120 | 27 % | 4 | 0.283 | 0.00 | 4.8 | 0 | 0/0 | 0.00 |
| random fixed-topo | All | 720 | 18 % | 5 | 0.363 | 0.00 | 4.7 | 0 | 0/0 | 0.00 |
| oracle | A | 140 | 56 % | 6 | 0 | 0.00 | 4.0 | 0 | 0/0 | 0.00 |
| oracle | B | 180 | 49 % | 7 | 0.00249 | 0.00 | 4.0 | 0 | 0/0 | 0.00 |
| oracle | C | 200 | 61 % | 2 | 0 | 0.00 | 3.9 | 0 | 0/0 | 0.00 |
| oracle | All | 520 | 56 % | 5 | 0 | 0.00 | 4.0 | 0 | 0/0 | 0.00 |

## Per target (successes / runs; median sims to success)

Defaults pass = the solution's chain at default settings already passes (analysis flag).

| Target | Cat. | Subset | Defaults pass | random catalog | random fixed-topo | oracle |
|---|---|---|---|---|---|---|
| G01 | A |  | no | 6/20 (6) | 4/20 (6.5) | 10/20 (5.5) |
| G02 | A |  | no | 4/20 (7) | 16/20 (5) | 16/20 (5) |
| G03 | A | ✓ | no | 11/20 (4) | 12/20 (5.5) | 12/20 (4.5) |
| G04 | A | ✓ | no | 5/20 (5) | 9/20 (7) | 9/20 (7) |
| G05 | A |  | no | 2/20 (4.5) | 5/20 (5) | 6/20 (7) |
| G06 | A |  | no | 4/20 (8) | 13/20 (8) | 13/20 (8) |
| G07 | A |  | no | 8/20 (5.5) | 20/20 (4) | 12/20 (4) |
| G08 | B | ✓ | no | 4/20 (6.5) | 1/20 (6) | 13/20 (5) |
| G09 | B |  | no | 9/20 (5) | 1/20 (3) | 8/20 (5) |
| G10 | B |  | no | 2/20 (9.5) | 1/20 (5) | 8/20 (10) |
| G11 | B |  | no | 1/20 (5) | 1/20 (5) | 12/20 (6.5) |
| G12 | B | ✓ | no | 3/20 (7) | 1/20 (7) | 9/20 (6) |
| G13 | B | ✓ | no | 4/20 (6.5) | 4/20 (8) | 11/20 (6) |
| G14 | B |  | no | 2/20 (10) | 1/20 (6) | 12/20 (7.5) |
| G15 | B |  | no | 2/20 (10.5) | 1/20 (6) | 10/20 (8) |
| G16 | B | ✓ | no | 4/20 (7) | 1/20 (6) | 6/20 (10) |
| G17 | C |  | yes | 1/20 (7) | 0/20 (–) | 20/20 (1) |
| G18 | C | ✓ | no | 0/20 (–) | 1/20 (7) | 6/20 (5.5) |
| G19 | C |  | no | 4/20 (6.5) | 1/20 (6) | 10/20 (5.5) |
| G20 | C |  | no | 2/20 (8.5) | 0/20 (–) | 9/20 (3) |
| G21 | C |  | no | 3/20 (8) | 0/20 (–) | 9/20 (7) |
| G22 | C |  | no | 2/20 (10.5) | 0/20 (–) | 10/20 (6.5) |
| G23 | C | ✓ | yes | 0/20 (–) | 0/20 (–) | 20/20 (1) |
| G24 | C |  | no | 2/20 (6) | 0/20 (–) | 7/20 (6) |
| G25 | C | ✓ | no | 0/20 (–) | 1/20 (3) | 11/20 (6) |
| G26 | C | ✓ | yes | 0/20 (–) | 0/20 (–) | 20/20 (1) |
| U1 | D |  | – | 0/20 (–) | 0/20 (–) | – |
| U2 | D |  | – | 0/20 (–) | 0/20 (–) | – |
| U3 | D | ✓ | – | 0/20 (–) | 0/20 (–) | – |
| U4 | D |  | – | 0/20 (–) | 0/20 (–) | – |
| H1 | A |  | – | 3/20 (7) | 3/20 (8) | – |
| H2 | A |  | – | 0/20 (–) | 0/20 (–) | – |
| H3 | A |  | – | 13/20 (6) | 5/20 (5) | – |
| H4 | A | ✓ | – | 9/20 (4) | 20/20 (3.5) | – |
| H5 | B |  | – | 18/20 (8) | 0/20 (–) | – |
| H6 | A |  | – | 5/20 (4) | 4/20 (5.5) | – |
