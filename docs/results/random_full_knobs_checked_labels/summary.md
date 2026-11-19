# Benchmark v1: summary

1960 finished runs from `runs\bench\v1_full_knobs`; methods: random_catalog, random_fixed_topology, random_fixed_topology_oracle; budget 12 sims. Success = all metrics in range (stop_reason all_pass). The oracle is not run on D or hand targets. Infrastructure errors left out (re-run): 0.

Labels: checked (`benchmarks/v1_labels_check.yaml`, scripts/reachability.py); changed: G08 B→A, G09 B→A, G10 B→A, G11 B→A, G12 B→A, G13 B→A, G14 B→A, G15 B→A, G16 B→A, G17 C→A, G18 C→A, G19 C→A, G20 C→A, G21 C→B, G23 C→A, G24 C→B, G25 C→A, G26 C→A.

Random-method knob range: random catalog: full knob range [0, 1] with end stops; random fixed-topo: full knob range [0, 1] with end stops; oracle: full knob range [0, 1] with end stops

Code commits per method (runs): random catalog: 501a876acd (modified) ×720; random fixed-topo: 8b37399d29 ×720; oracle: 8b37399d29 ×520

## Full set

Success rate (successful runs / runs, 95 % Wilson interval).

| Group | random catalog | random fixed-topo | oracle |
|---|---|---|---|
| A | 17 % (78/460) [14–21] | 20 % (94/460) [17–24] | 57 % (263/460) [53–62] |
| B | 12 % (5/40) [5–26] | 0 % (0/40) [0–9] | 40 % (16/40) [26–55] |
| C | 10 % (2/20) [3–30] | 0 % (0/20) [0–16] | 50 % (10/20) [30–70] |
| D | 0 % (0/80) [0–5] | 0 % (0/80) [0–5] | – |
| Hand | 40 % (48/120) [32–49] | 27 % (32/120) [20–35] | – |
| All | 18 % (133/720) [16–21] | 18 % (126/720) [15–20] | 56 % (289/520) [51–60] |

## Subset view (12 targets: G03, G04, G08, G12, G13, G16, G18, G23, G25, G26, H4, U3); all methods on exactly these targets (random methods filtered from their full-set runs)

Success rate (successful runs / runs, 95 % Wilson interval).

| Group | random catalog | random fixed-topo | oracle |
|---|---|---|---|
| A | 16 % (31/200) [11–21] | 15 % (30/200) [11–21] | 58 % (117/200) [52–65] |
| D | 0 % (0/20) [0–16] | 0 % (0/20) [0–16] | – |
| Hand | 45 % (9/20) [26–66] | 100 % (20/20) [84–100] | – |
| All | 17 % (40/240) [12–22] | 21 % (50/240) [16–26] | 58 % (117/200) [52–65] |

## C split (full set)

C targets split by whether the solution's chain at its default settings already passes (analysis flag from `scripts/flag_defaults.py`).

| C targets | random catalog | random fixed-topo | oracle |
|---|---|---|---|
| chain at defaults passes (none) | – | – | – |
| needs tuning (G22) | 10 % (2/20) | 0 % (0/20) | 50 % (10/20) |

## C split (subset)

C targets split by whether the solution's chain at its default settings already passes (analysis flag from `scripts/flag_defaults.py`).

| C targets | random catalog | random fixed-topo | oracle |
|---|---|---|---|
| chain at defaults passes (none) | – | – | – |
| needs tuning (none) | – | – | – |

## Block order, full set (2-block chains)

Runs that simulated at least one 2-block chain; of those, runs that tried the same two blocks in both orders. C targets: runs that tried the solution's order vs only the reversed order (solution chain from the analysis file).

| Method | Runs | With a 2-block chain | Both orders of a pair | C runs | C: solution order tried | C: only reversed order tried |
|---|---|---|---|---|---|---|
| random catalog | 720 | 696 | 96 | 20 | 7 | 9 |
| random fixed-topo | 720 | 0 | 0 | 20 | 0 | 0 |
| oracle | 520 | 300 | 0 | 20 | 20 | 0 |

## Block order, subset (2-block chains)

Runs that simulated at least one 2-block chain; of those, runs that tried the same two blocks in both orders. C targets: runs that tried the solution's order vs only the reversed order (solution chain from the analysis file).

| Method | Runs | With a 2-block chain | Both orders of a pair | C runs | C: solution order tried | C: only reversed order tried |
|---|---|---|---|---|---|---|
| random catalog | 240 | 233 | 31 | 0 | 0 | 0 |
| random fixed-topo | 240 | 0 | 0 | 0 | 0 | 0 |
| oracle | 200 | 140 | 0 | 0 | 0 | 0 |

## Details (full set)

| Method | Group | Runs | Success | Median sims to success | Median best score | Mean topology changes | Median wall s | Flagged runs | Tokens in/out | API-equivalent cost USD (no per-token billing) |
|---|---|---|---|---|---|---|---|---|---|---|
| random catalog | A | 460 | 17 % | 7 | 0.276 | 8.44 | 5.2 | 0 | 0/0 | 0.00 |
| random catalog | B | 40 | 12 % | 8 | 0.399 | 8.75 | 5.2 | 0 | 0/0 | 0.00 |
| random catalog | C | 20 | 10 % | 10.5 | 0.457 | 9.10 | 5.2 | 0 | 0/0 | 0.00 |
| random catalog | D | 80 | 0 % | – | 0.794 | 9.20 | 5.2 | 0 | 0/0 | 0.00 |
| random catalog | Hand | 120 | 40 % | 5.5 | 0.0463 | 7.26 | 4.8 | 0 | 0/0 | 0.00 |
| random catalog | All | 720 | 18 % | 7 | 0.323 | 8.36 | 5.2 | 0 | 0/0 | 0.00 |
| random fixed-topo | A | 460 | 20 % | 6 | 0.301 | 0.00 | 4.7 | 0 | 0/0 | 0.00 |
| random fixed-topo | B | 40 | 0 % | – | 0.383 | 0.00 | 4.7 | 0 | 0/0 | 0.00 |
| random fixed-topo | C | 20 | 0 % | – | 0.447 | 0.00 | 4.8 | 0 | 0/0 | 0.00 |
| random fixed-topo | D | 80 | 0 % | – | 0.69 | 0.00 | 4.7 | 0 | 0/0 | 0.00 |
| random fixed-topo | Hand | 120 | 27 % | 4 | 0.283 | 0.00 | 4.8 | 0 | 0/0 | 0.00 |
| random fixed-topo | All | 720 | 18 % | 5 | 0.363 | 0.00 | 4.7 | 0 | 0/0 | 0.00 |
| oracle | A | 460 | 57 % | 4 | 0 | 0.00 | 3.9 | 0 | 0/0 | 0.00 |
| oracle | B | 40 | 40 % | 6.5 | 0.0322 | 0.00 | 7.1 | 0 | 0/0 | 0.00 |
| oracle | C | 20 | 50 % | 6.5 | 0.00691 | 0.00 | 6.3 | 0 | 0/0 | 0.00 |
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
| G08 | A | ✓ | no | 4/20 (6.5) | 1/20 (6) | 13/20 (5) |
| G09 | A |  | no | 9/20 (5) | 1/20 (3) | 8/20 (5) |
| G10 | A |  | no | 2/20 (9.5) | 1/20 (5) | 8/20 (10) |
| G11 | A |  | no | 1/20 (5) | 1/20 (5) | 12/20 (6.5) |
| G12 | A | ✓ | no | 3/20 (7) | 1/20 (7) | 9/20 (6) |
| G13 | A | ✓ | no | 4/20 (6.5) | 4/20 (8) | 11/20 (6) |
| G14 | A |  | no | 2/20 (10) | 1/20 (6) | 12/20 (7.5) |
| G15 | A |  | no | 2/20 (10.5) | 1/20 (6) | 10/20 (8) |
| G16 | A | ✓ | no | 4/20 (7) | 1/20 (6) | 6/20 (10) |
| G17 | A |  | yes | 1/20 (7) | 0/20 (–) | 20/20 (1) |
| G18 | A | ✓ | no | 0/20 (–) | 1/20 (7) | 6/20 (5.5) |
| G19 | A |  | no | 4/20 (6.5) | 1/20 (6) | 10/20 (5.5) |
| G20 | A |  | no | 2/20 (8.5) | 0/20 (–) | 9/20 (3) |
| G21 | B |  | no | 3/20 (8) | 0/20 (–) | 9/20 (7) |
| G22 | C |  | no | 2/20 (10.5) | 0/20 (–) | 10/20 (6.5) |
| G23 | A | ✓ | yes | 0/20 (–) | 0/20 (–) | 20/20 (1) |
| G24 | B |  | no | 2/20 (6) | 0/20 (–) | 7/20 (6) |
| G25 | A | ✓ | no | 0/20 (–) | 1/20 (3) | 11/20 (6) |
| G26 | A | ✓ | yes | 0/20 (–) | 0/20 (–) | 20/20 (1) |
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
