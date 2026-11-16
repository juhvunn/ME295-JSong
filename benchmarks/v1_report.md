# Benchmark set v1: generation report

Seed 1116, commit `0c9e96d94a`, generated 2026-11-16T18:10:01+00:00, 764 s.

Model files: `models/opamps.lib` (validated, `385958e12a80…`), `models/diodes_fitted.lib` (validated, `06dade94cbf2…`), `models/bjts_fitted.lib` (validated, `b1458826f0ee…`)

Categories: {'A': 12, 'B': 10, 'C': 10, 'D': 4}

Rules: **draws_per_chain**: 250; **quotas**: {'A': 7, 'B': 9, 'C': 10, 'D': 4}; **base_windows**: gain/ac_peak_db +-1.5 dB; thd/ac_peak_hz x/1.25; out_pk x/1.2; even_odd x/1.5 (>= +-0.02); calibration multiplies the half-width (dB, even_odd) or the exponent; **calibration**: smallest factor in [1.0, 1.15, 1.3, 1.5, 1.75, 2.0, 2.3, 2.6, 3.0, 3.5, 4.0] with hit rate (passes / draws on the solution's chain, generator distribution) >= 0.05; capped at 4.0; a target still below at the cap is discarded and redrawn; **floors**: solution out_pk_v >= 0.05 V; thd_pct used only if THD >= 0.0013 % (10 x measured floor 0.00013 %); even_odd only if THD >= 1.0 %; **eligibility**: 10-90 % spread over playable pool (meaningful values) >= 2 x base window width; **sampling**: generator distribution (sampling.generator_params): knobs Beta(0.5,0.5) on [0,1], default choice 25 %, parts log-uniform snapped to E-series; validated choices only

Generation statistics: attempts 544, dc_or_sim_failure 107, too_quiet 218, too_few_eligible_metrics 0, calibration_capped 132, excluded_default_passes 2, self_check_failed 0, category_full 59, pool_valid {'dist_distplus': 250, 'fuzz_ff_si': 160, 'od_ts808': 250, 'dist_distplus -> od_ts808': 250, 'fuzz_ff_si -> dist_distplus': 156, 'fuzz_ff_si -> od_ts808': 154, 'od_ts808 -> dist_distplus': 250}, unreachable_pairs_tried 11, seconds 764

od_ts808 at its defaults (exclusion reference): gain_1k_db 13.4, ac_peak_db 13.5, ac_peak_hz 873, thd_pct 8.42, even_odd 0.0219, out_pk_v 0.224

## Metric spreads per chain (playable pool, meaningful values; 10 / 50 / 90 %; ✓ = eligible)

| Chain | gain_1k_db | thd_pct | ac_peak_hz | ac_peak_db | even_odd | out_pk_v |
|---|---|---|---|---|---|---|
| dist_distplus | -4.55 / 14.3 / 32.6 (n=156) ✓ | 9.68 / 29.9 / 41.1 (n=131) ✓ | 2.64e+03 / 2.64e+03 / 2.64e+03 (n=156) ✗ | 6.68 / 25.8 / 44.7 (n=156) ✓ | 0.00191 / 0.0657 / 0.0766 (n=126) ✗ | 0.0786 / 0.397 / 1.48 (n=156) ✓ |
| fuzz_ff_si | -0.881 / 11 / 28.6 (n=64) ✓ | 32.1 / 40.6 / 47.3 (n=64) ✗ | 145 / 191 / 327 (n=64) ✗ | 6.69 / 18.4 / 34.2 (n=64) ✓ | 0.3 / 1.02 / 1.88 (n=64) ✗ | 0.0635 / 0.144 / 0.226 (n=64) ✓ |
| od_ts808 | -0.58 / 15.1 / 29.1 (n=206) ✓ | 5.1 / 10.7 / 16.6 (n=206) ✓ | 399 / 726 / 4.38e+03 (n=206) ✓ | 0.489 / 16.3 / 30.8 (n=206) ✓ | 0.014 / 0.0509 / 0.506 (n=200) ✓ | 0.117 / 0.561 / 1.61 (n=206) ✓ |
| dist_distplus → od_ts808 | 2.41 / 25.7 / 50 (n=167) ✓ | 5.88 / 14.1 / 19.3 (n=167) ✓ | 2.52e+03 / 2.52e+03 / 2.64e+03 (n=167) ✗ | 10.4 / 32.1 / 56.3 (n=167) ✓ | 0.0279 / 0.0809 / 0.323 (n=158) ✓ | 0.111 / 0.419 / 1.46 (n=167) ✓ |
| fuzz_ff_si → dist_distplus | -0.141 / 22.5 / 45.3 (n=58) ✓ | 19.1 / 32.7 / 40.4 (n=58) ✗ | 166 / 296 / 551 (n=58) ✓ | 6.7 / 30.3 / 49.4 (n=58) ✓ | 0.157 / 0.496 / 1.64 (n=58) ✓ | 0.0783 / 0.25 / 1 (n=58) ✓ |
| fuzz_ff_si → od_ts808 | 4.49 / 18.9 / 44.2 (n=81) ✓ | 13.1 / 18 / 26.6 (n=81) ✗ | 264 / 399 / 577 (n=81) ✗ | 8.52 / 25.6 / 47.8 (n=81) ✓ | 0.245 / 0.932 / 2.55 (n=81) ✓ | 0.0873 / 0.282 / 1.06 (n=81) ✓ |
| od_ts808 → dist_distplus | 5.91 / 27.4 / 56.8 (n=145) ✓ | 7.88 / 28.9 / 41.7 (n=145) ✓ | 426 / 796 / 1.38e+03 (n=145) ✓ | 7.39 / 28.1 / 58.1 (n=145) ✓ | 0.0119 / 0.0657 / 0.131 (n=145) ✓ | 0.0742 / 0.38 / 1.82 (n=145) ✓ |

Spread measure: dB metrics p90−p10 (needs ≥ 6 dB); thd/ac_peak_hz/out_pk log10(p90/p10) (needs ≥ 0.388 / 0.388 / 0.317 decades); even_odd p90−p10 ≥ 2 × window width at the median; n ≥ 20.

## Targets

| Id | Source | Cat. | Targets | Factor | Hit rate (at factor 1) | Start chain pass | Single blocks pass | Pool pass |
|---|---|---|---|---|---|---|---|---|
| G01 | generated | A | gain_1k_db 14.88–26.88; ac_peak_db 26.8–38.8; out_pk_v 0.2031–0.8731 | 4 | 0.056 (0.004) | 3/250 | dist_distplus 14, fuzz_ff_si 3, od_ts808 3 | 44/1470 |
| G02 | generated | A | gain_1k_db 4.736–13.74; ac_peak_hz 2240–8546; even_odd 0.007918–0.2292 | 3 | 0.052 (0.008) | 13/250 | dist_distplus 21, fuzz_ff_si 0, od_ts808 13 | 59/1470 |
| G03 | generated | A | thd_pct 8.5–40.53; ac_peak_db 11.29–21.79; out_pk_v 0.1356–0.4858 | 3.5 | 0.056 (0.008) | 13/250 | dist_distplus 14, fuzz_ff_si 16, od_ts808 13 | 81/1470 |
| G04 | generated | A | gain_1k_db 16.29–28.29; thd_pct 5.343–31.85; ac_peak_hz 1792–10680; out_pk_v 0.4245–1.825 | 4 | 0.056 (0.000) | 14/250 | dist_distplus 10, fuzz_ff_si 0, od_ts808 14 | 38/1470 |
| G05 | generated | A | gain_1k_db 9.064–19.56; ac_peak_db 19.65–30.15; out_pk_v 0.8237–2.951 | 3.5 | 0.060 (0.012) | 6/250 | dist_distplus 15, fuzz_ff_si 0, od_ts808 6 | 29/1470 |
| G06 | generated | A | thd_pct 5.456–11.91; ac_peak_hz 390.3–852.4; out_pk_v 0.3342–0.6327 | 1.75 | 0.060 (0.012) | 15/250 | dist_distplus 0, fuzz_ff_si 0, od_ts808 15 | 17/1470 |
| G07 | generated | A | gain_1k_db 0.9097–12.91; thd_pct 2.067–12.32; even_odd 0–0.3889 | 4 | 0.052 (0.000) | 37/250 | dist_distplus 4, fuzz_ff_si 0, od_ts808 37 | 66/1470 |
| G08 | generated | B | thd_pct 6.04–36; ac_peak_db 42.31–54.31; even_odd 0.01594–0.4857; out_pk_v 0.4019–1.728 | 4 | 0.056 (0.000) | 0/250 | dist_distplus 3, fuzz_ff_si 0, od_ts808 0 | 23/1470 |
| G09 | generated | B | gain_1k_db -1.52–10.48; thd_pct 14.04–83.69; ac_peak_db 10.05–22.05; out_pk_v 0.05608–0.2412 | 4 | 0.052 (0.000) | 0/250 | dist_distplus 13, fuzz_ff_si 19, od_ts808 0 | 48/1470 |
| G10 | generated | B | thd_pct 18.75–89.43; ac_peak_db 39.64–50.14; out_pk_v 0.479–1.717 | 3.5 | 0.052 (0.000) | 0/250 | dist_distplus 13, fuzz_ff_si 0, od_ts808 0 | 29/1470 |
| G11 | generated | B | gain_1k_db 21.34–33.34; thd_pct 16.57–98.79; ac_peak_db 21.39–33.39; out_pk_v 0.1434–0.6164 | 4 | 0.056 (0.008) | 0/250 | dist_distplus 3, fuzz_ff_si 2, od_ts808 0 | 27/1470 |
| G12 | generated | B | thd_pct 20.84–66.5; ac_peak_db 30.04–37.84; even_odd 0.01769–0.2 | 2.6 | 0.064 (0.024) | 0/250 | dist_distplus 22, fuzz_ff_si 0, od_ts808 0 | 41/1470 |
| G13 | generated | B | ac_peak_db 33.45–45.45; even_odd 0.002437–0.4173; out_pk_v 0.164–0.705 | 4 | 0.052 (0.008) | 0/250 | dist_distplus 17, fuzz_ff_si 2, od_ts808 0 | 57/1470 |
| G14 | generated | B | gain_1k_db 17.9–24.8; thd_pct 25.06–69.95; ac_peak_db 29.04–35.94 | 2.3 | 0.056 (0.004) | 0/250 | dist_distplus 14, fuzz_ff_si 2, od_ts808 0 | 21/1470 |
| G15 | generated | B | gain_1k_db 27.38–39.38; thd_pct 16.45–98.08; ac_peak_db 43.07–55.07 | 4 | 0.052 (0.000) | 0/250 | dist_distplus 13, fuzz_ff_si 0, od_ts808 0 | 19/1470 |
| G16 | generated | B | gain_1k_db 10.39–16.39; thd_pct 18.57–45.33; ac_peak_db 20.66–26.66 | 2 | 0.060 (0.004) | 0/250 | dist_distplus 15, fuzz_ff_si 3, od_ts808 0 | 26/1470 |
| G17 | generated | C | gain_1k_db 12.88–19.78; thd_pct 16.42–45.83; ac_peak_hz 522.6–1459 | 2.3 | 0.060 (0.004) | 0/250 | dist_distplus 0, fuzz_ff_si 0, od_ts808 0 | 19/1470 |
| G18 | generated | C | gain_1k_db 28.65–36.45; thd_pct 16–51.04; ac_peak_db 30.16–37.96; even_odd 0.01105–0.1809 | 2.6 | 0.056 (0.008) | 0/250 | dist_distplus 0, fuzz_ff_si 0, od_ts808 0 | 16/1470 |
| G19 | generated | C | gain_1k_db 38.87–50.87; thd_pct 6.223–37.09; out_pk_v 0.2118–0.9108 | 4 | 0.060 (0.004) | 0/250 | dist_distplus 0, fuzz_ff_si 0, od_ts808 0 | 27/1470 |
| G20 | generated | C | thd_pct 23.76–75.82; ac_peak_hz 488.7–1560; even_odd 0.01756–0.1996; out_pk_v 0.2815–0.7265 | 2.6 | 0.072 (0.000) | 0/250 | dist_distplus 0, fuzz_ff_si 0, od_ts808 0 | 19/1470 |
| G21 | generated | C | gain_1k_db 44.38–53.38; thd_pct 8.214–31.34; even_odd 0.00509–0.2197 | 3 | 0.060 (0.012) | 0/250 | dist_distplus 0, fuzz_ff_si 0, od_ts808 0 | 20/1470 |
| G22 | generated | C | gain_1k_db 48.07–58.57; thd_pct 12.23–58.34; ac_peak_hz 399.8–1906; even_odd 0.01765–0.3623 | 3.5 | 0.052 (0.000) | 0/250 | dist_distplus 0, fuzz_ff_si 0, od_ts808 0 | 15/1470 |
| G23 | generated | C | thd_pct 16.63–79.28; ac_peak_hz 459–2189; even_odd 0–0.2441; out_pk_v 0.0298–0.1068 | 3.5 | 0.056 (0.004) | 0/250 | dist_distplus 0, fuzz_ff_si 0, od_ts808 0 | 16/1470 |
| G24 | generated | C | gain_1k_db 41.26–50.26; thd_pct 7.011–26.74; ac_peak_db 50.27–59.27 | 3 | 0.056 (0.000) | 0/250 | dist_distplus 0, fuzz_ff_si 0, od_ts808 0 | 14/1470 |
| G25 | generated | C | gain_1k_db 23.63–30.53; thd_pct 24.61–68.69; ac_peak_hz 628.3–1754; ac_peak_db 23.64–30.54 | 2.3 | 0.056 (0.012) | 0/250 | dist_distplus 0, fuzz_ff_si 0, od_ts808 0 | 14/1470 |
| G26 | generated | C | thd_pct 23.95–37.42; ac_peak_hz 637–995.3; even_odd 0.03097–0.07646 | 1 | 0.060 (0.060) | 0/250 | dist_distplus 0, fuzz_ff_si 0, od_ts808 0 | 15/1470 |
| U1 | generated | D | gain_1k_db 43.47–; thd_pct –7.599 | – | 0 | 0/250 | dist_distplus 0, fuzz_ff_si 0, od_ts808 0 | 0/1470 |
| U2 | generated | D | even_odd 1.694–; ac_peak_hz 4376– | – | 0 | 0/250 | dist_distplus 0, fuzz_ff_si 0, od_ts808 0 | 0/1470 |
| U3 | generated | D | thd_pct 42.13–; ac_peak_hz 4376– | – | 0 | 0/250 | dist_distplus 0, fuzz_ff_si 0, od_ts808 0 | 0/1470 |
| U4 | generated | D | gain_1k_db 60.06–; even_odd 2.28– | – | 0 | 0/250 | dist_distplus 0, fuzz_ff_si 0, od_ts808 0 | 0/1470 |
| H1 | hand | A | thd_pct 15–30; gain_1k_db 10–; ac_peak_hz 600–1200 | – | best chain 0.064 | 9/250 | dist_distplus 0, fuzz_ff_si 0, od_ts808 9 | 33/1470 |
| H2 | hand | A | thd_pct –2; gain_1k_db 12– | – | best chain 0.012 | 1/250 | dist_distplus 3, fuzz_ff_si 0, od_ts808 1 | 4/1470 |
| H3 | hand | A | thd_pct 25–; ac_peak_hz 2000– | – | best chain 0.524 | 2/250 | dist_distplus 131, fuzz_ff_si 2, od_ts808 2 | 162/1470 |
| H4 | hand | A | thd_pct 3–10; ac_peak_hz –700 | – | best chain 0.208 | 52/250 | dist_distplus 0, fuzz_ff_si 0, od_ts808 52 | 88/1470 |
| H5 | hand | B | even_odd 0.8–; thd_pct 30– | – | best chain 0.428 | 0/250 | dist_distplus 0, fuzz_ff_si 107, od_ts808 0 | 154/1470 |
| H6 | hand | A | even_odd 0.3–; thd_pct 15–; ac_peak_hz 500–1200 | – | best chain 0.108 | 10/250 | dist_distplus 0, fuzz_ff_si 4, od_ts808 10 | 56/1470 |

## Hand-written targets: hit rate per chain (passes / draws)

| Id | dist_distplus | fuzz_ff_si | od_ts808 | dist_distplus -> od_ts808 | fuzz_ff_si -> dist_distplus | fuzz_ff_si -> od_ts808 | od_ts808 -> dist_distplus |
|---|---|---|---|---|---|---|---|
| H1 | 0.000 | 0.000 | 0.036 | 0.000 | 0.004 | 0.028 | 0.064 |
| H2 | 0.012 | 0.000 | 0.004 | 0.000 | 0.000 | 0.000 | 0.000 |
| H3 | 0.524 | 0.008 | 0.008 | 0.060 | 0.000 | 0.000 | 0.048 |
| H4 | 0.000 | 0.000 | 0.208 | 0.020 | 0.000 | 0.024 | 0.100 |
| H5 | 0.000 | 0.428 | 0.000 | 0.000 | 0.140 | 0.048 | 0.000 |
| H6 | 0.000 | 0.016 | 0.040 | 0.000 | 0.048 | 0.108 | 0.012 |
