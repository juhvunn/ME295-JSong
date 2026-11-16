# Part models

`smoke_models.lib` contains **placeholder models only** (generic parameters, chosen to check
netlist syntax, connectivity and DC bias). Every metric measured so far, including
`typical_metrics` in each `block.yaml`, comes from these placeholders. They must be replaced with
real part models before Phase 3 results are collected.

## Required models

The names must match exactly, because block templates refer to them by name: `models:` in each
`blocks/<id>/block.yaml`, and the `Q_model` choices of `fuzz_ff_si`.

| Name in our netlists | Real part | Kind | Pins / terminals our templates use | Used by | Suggested source | Status |
|---|---|---|---|---|---|---|
| `JRC4558_HALF` | NJM/JRC4558 (one half of the dual op-amp) | `.subckt` | `inp inn vcc vee out` | od_ts808 (IC1a, IC1b) | Our macromodel, `opamps.lib` (values from the Nisshinbo datasheet) | **done** (A1) |
| `LM741` | LM741 | `.subckt` | `inp inn vcc vee out` | dist_distplus | Our macromodel, `opamps.lib` (values from the TI datasheet); slew rate matters for this pedal | **done** (A1) |
| `Q2N4401` | 2N4401 NPN | `.model … NPN` | standard `C B E` | od_ts808 (input/output buffers) | Manufacturer model (e.g. onsemi) | needed |
| `Q2N3904` | 2N3904 NPN | `.model … NPN` | standard `C B E` | fuzz_ff_si (`Q_model` choice) | Manufacturer model (e.g. onsemi) | needed |
| `QBC109C` | BC109C NPN | `.model … NPN` | standard `C B E` | fuzz_ff_si (`Q_model` choice) | Legacy Philips/NXP library, or a BC549C model as a modern equivalent (say which) | needed |
| `D1N914` | 1N914 / 1N4148 silicon diode | `.model … D` | standard `A K` | od_ts808, dist_distplus (`D_clip=si`) | Fitted to onsemi typical curves, `diodes_fitted.lib` | **done** (A2) |
| `DGE` | Germanium diode, 1N34A as a stand-in for the original MXR's 1N270 | `.model … D` | standard `A K` | dist_distplus (`D_clip=ge`) | No datasheet I-V data found: **unvalidated placeholder**, `D_clip=ge` rejected by Validate | **unvalidated** (A2, option 4) |
| `DLED_RED` | Kingbright WP7113ID 5 mm red LED | `.model … D` | standard `A K` | od_ts808, dist_distplus (`D_clip=led`) | Fitted to Kingbright typical curve (0.1–10 mA), `diodes_fitted.lib`; µA region extrapolated | **done** (A2) |

`fuzz_ff_si` has no `models:` entry: the transistor model *is* the `Q_model` choice
(`Q2N3904` or `QBC109C`).

## Op-amps: our behavioural macromodel (`opamps.lib`)

`OPAMP_MACRO` (single pole, tanh-limited transconductance so that SR = IMAX/C, diode-clamped
integrator for output limits, ROUT in series), plus two wrappers with the datasheet values.
Validated by `tests/test_models.py`.

**Sources** (downloaded 2026-11-16 from the manufacturers' sites; PDFs are not committed because
of copyright. The SHA-256 identifies the exact file read.)

| Ref | Document | URL | SHA-256 |
|---|---|---|---|
| [NJM] | Nisshinbo Micro Devices, NJM4558 datasheet, Ver. 20260723 (4 pages) | https://www.nisshinbo-microdevices.co.jp/en/pdf/datasheet/NJM4558_E.pdf | `9d73cf4cc7b5fa8c9fac83c0f5bd58e8571e7076fca57456a2b689cb5c39acbe` |
| [TI] | Texas Instruments, LM741 datasheet, SNOSC25D (May 1998, revised Oct 2015) | https://www.ti.com/lit/ds/symlink/lm741.pdf | `6f3bf3cbce352c73a8f3e7506023ab1f5d12549834840e0227d6bb37de6c48db` |

**Values** (typical values at ±15 V, 25 °C, unless noted)

| Param | `JRC4558_HALF` | Source | `LM741` | Source |
|---|---|---|---|---|
| AOL | 1e5 (100 dB) | [NJM] p.2, AV, RL ≥ 2 kΩ | 2e5 (200 V/mV) | [TI] p.5, §6.5, RL ≥ 2 kΩ |
| GBW | 3 MHz | [NJM] p.2, GB | 1.17 MHz | **derived**: [TI] p.5 rise time 0.3 µs, BW = 0.35/rise time from p.6 note (2). The LM741 row has no bandwidth value. |
| SR | 1 V/µs | [NJM] p.2 | 0.5 V/µs | [TI] p.5, unity gain |
| IB | 25 nA | [NJM] p.2 | 80 nA | [TI] p.5 |
| RIN | 5 MΩ | [NJM] p.2 | 2 MΩ | [TI] p.5 (measured at ±20 V) |
| Output swing | 2 V from each rail at RL = 2 kΩ, **constant vs supply** | [NJM] p.2 (VOM2 ±13 V) and p.4 graph "Maximum Output Voltage Swing vs. Operating Voltage" (+4 V at ±6 V … +12 V at ±14 V) | 2 V from each rail at RL = 2 kΩ | [TI] p.5 (±13 V at ±15 V). **No swing-vs-supply graph: constant headroom assumed** (decision D6). |
| ROUT | 50 Ω | **assumption** (not in the datasheet) | 50 Ω | **assumption** (not in the datasheet) |
| VDROP (internal clamp) | 1.9 V | set so that ±6 V, RL = 2 kΩ gives ±4.0 V (lowest graph point, closest to the 9 V pedal supply): 1.9 + 50 Ω × 2 mA = 2.0 V | 1.675 V | set so that ±15 V, RL = 2 kΩ gives ±13 V: 1.675 + 50 Ω × 6.5 mA = 2.0 V |

**Validation results** (`python -m pytest -s tests/test_models.py`; tolerances: GBW and SR ±10 %, AOL ±1 dB, swing ±0.15 V)

| Check | JRC4558_HALF | LM741 |
|---|---|---|
| GBW (gain-of-101 amplifier, −3 dB × 101) | 2.994 MHz | 1.167 MHz |
| SR (follower, 10 V step, 10–90 %) | 0.995 V/µs | 0.498 V/µs |
| AOL (at 0.01 Hz) | 99.8 dB | 105.8 dB |
| Swing ±15 V, 2 kΩ | ±12.85 V (datasheet ±13) | ±13.07 V (datasheet ±13) |
| Swing ±6 V, 2 kΩ | ±4.07 V (graph ±4.0) | — |
| 9 V single supply, 2 kΩ to 4.5 V (extrapolated, report only) | 1.89 … 7.11 V | 1.68 … 7.33 V |

**Known limits.**
- The single-resistor output model cannot match both the ±15 V table and the low-supply graph
  for the NJM4558. It is calibrated to the graph point nearest the pedal's operating point, so
  with a light load (10 kΩ) at ±15 V it gives about 1 V less swing than the table (±14 V).
- The LM741's recommended supply is ±10 V minimum ([TI] p.4, §6.3). A 9 V Distortion+ runs it
  outside its specified range, so the model's behaviour there is an extrapolation, as is the
  real pedal's.
- Not modelled: input offset, common-mode input range, noise, supply current, second poles,
  temperature.

## Diodes: fitted models (`diodes_fitted.lib`)

`scripts/fit_diodes.py` fits `Is, N, Rs` of the SPICE diode equation
`V = N·Vt·ln(I/Is + 1) + I·Rs` (Vt at 25 °C; `Tnom=25` in each `.model`) by least squares on the
voltage error. The points and their sources are in `models/diode_points.yaml`; the `.lib` file is
generated (edit the YAML, then run `python -m scripts.fit_diodes`). Validated by
`tests/test_models.py` (ngspice reproduces every fit point within ±20 mV for silicon, ±3 % for the LED).

**How the points were read.** The datasheet curves are vector graphics. Their vertex coordinates
were extracted from the PDF (PyMuPDF `get_drawings`) and converted to amps and volts using the
plot's grid lines (or frame and tick labels where no grid lines exist). This avoids reading
values by eye. Uncertainty is a fraction of a grid step, except where stated below.

**Sources** (downloaded 2026-11-16; PDFs not committed)

| Ref | Document | URL | SHA-256 |
|---|---|---|---|
| [ONS] | onsemi, Small Signal Diode 1N91x, 1N4x48, FDLL914, FDLL4x48, publication 1N914/D, Rev. 6 (Sept 2024) | https://www.onsemi.com/pdf/datasheet/1n914-d.pdf | `70b7437841e5ace17185a8630e6eb245322f5337d0f72408a3f37cb7cf4b0147` |
| [KB] | Kingbright WP7113ID (5 mm High Efficiency Red), Spec No. DSAF0012 / 1101005042, Rev V.14A, 01/08/2026 | https://www.kingbrightusa.com/images/catalog/SPEC/WP7113ID.pdf | `b5bb33f69c13fd92ab6d47a8fd71168b6e7ee685139c8f381957aeea9286c9da` |
| [TAI] | Taitron 1N34A Germanium Glass Diode, Rev. A/AH (not used for a fit, see below) | https://www.taitroncomponents.com/catalog/Datasheet/1N34A.pdf | `2f8cf1a1e92822a9c1921b8c934d944ca91d36ff9f33b6b06fd22de890ccd57c` |

### `D1N914` (1N914 / 1N4148)

- **Data:** typical curves at 25 °C: [ONS] Fig. 3 (1–100 µA) and Fig. 4 (0.1–10 mA), p.3; 13 points.
  The two figures agree within 2 mV at 100 µA.
- **Fit (1 µA–10 mA):** Is = 4.179 nA, N = 1.938, Rs = 0.401 Ω. **Max error 1.4 mV, rms 0.5 mV.**
- **Above the fit range** ([ONS] Fig. 5, not fitted; current read from tick labels, ±3 %): model
  −4 mV at 20 mA, −10 mV at 50 mA, −30 mV at 100 mA. The pedals stay well below 10 mA (see the
  operating currents below).
- **Below the fit range (extrapolated):** 0.160 V at 100 nA, 0.061 V at 10 nA.
- **Capacitance:** Cjo = 0.87 pF, M = 0.026 (VJ = 1 V, ngspice default), from [ONS] Fig. 7, p.4
  (typical: 0.87 pF at 0 V, 0.81 pF at 15 V). The figure does not say which part variant it shows.
  The p.2 table gives only maxima (4.0 pF for 914/4148).
- **Not modelled:** reverse recovery (trr ≤ 4 ns max, p.2; irrelevant at audio frequencies), breakdown.

### `DLED_RED` (Kingbright WP7113ID)

- **Data:** typical I-V curve at 25 °C, [KB] p.3, "Forward Current vs. Forward Voltage", plus the
  p.2 table (VF typ 1.9 V at 10 mA; the curve gives 1.902 V at 9.94 mA).
- **Resolution:** the curve has linear axes (0–20 mA, 1.3–2.3 V). One PDF point = 0.22 mA and 10 mV,
  so points below ~1 mA carry about ±0.1 mA uncertainty. **The lowest datasheet point is 0.107 mA;
  everything below it is extrapolated.**
- **Fit (0.1–10 mA, decision (b), where clipping LEDs operate):** Is = 9.417e-19 A, N = 1.837,
  Rs = 17.12 Ω. **Max error 9.5 mV, rms 5.2 mV.**
- **Above the fit range** (not fitted): +22 mV at 11.2 mA, +32 mV at 12.4 mA, +66 mV at 15 mA, +115 mV at 20 mA.
- **Below the fit range (extrapolated):** 1.419 V at 10.7 µA, 1.310 V at 1.07 µA, 1.202 V at 0.107 µA.
- **Not modelled:** capacitance (not in the datasheet), breakdown.
- **Why (b):** a single-exponential model cannot follow this LED's curve over 0.1–20 mA. Fitting
  the whole range leaves a systematic 25 mV error; fitting 0.1–10 mA gives 9.5 mV where it matters.

**The extrapolation is not pinned down by the datasheet.** Fitting different parts of the curve
gives very different low-current behaviour:

| Fit range | Max error in range | V at 1 µA (extrapolated) |
|---|---|---|
| 1–20 mA | 11.3 mV | 0.962 V |
| 0.1–20 mA | 24.8 mV | 1.230 V |
| **0.1–10 mA (used)** | **9.5 mV** | **1.307 V** |

### Operating currents in the pedals

From `python -m scripts.diode_study`: default settings, 1 kHz, 300 mV pickup EMF. This uses our
op-amp and fitted diode models, with the transistors still placeholders until step B. The current
is computed from the simulated diode voltage with the fitted diode equation.

| Block, D_clip | Peak current | Time <1 µA | 1–100 µA | 0.1–1 mA | >1 mA |
|---|---|---|---|---|---|
| od_ts808, si | 40.5 µA | 5 % | 95 % | 0 % | 0 % |
| od_ts808, led | 31.7 µA | 18 % | 82 % | 0 % | 0 % |
| dist_distplus, si | 201 µA | 4 % | 13 % | 83 % | 0 % |
| dist_distplus, led | 105.5 µA | 15 % | 31 % | 54 % | 0 % |

The TS-808 clipping diodes work at 1–100 µA, as estimated. The Distortion+ diodes work mostly at
0.1–1 mA (op-amp swing of about ±2.5 V across R9 = 10 kΩ). **The TS-808 LEDs operate entirely below
the lowest LED datasheet point (0.107 mA)**, so `D_clip=led` results in that block rest on the
extrapolation.

### LED sensitivity (low and high ends of the extrapolation range)

`D_clip=led`, default settings; same model set as above.

| Block | Metric | Low (0.962 V at 1 µA) | Mid (1.230 V) | Used (1.307 V) | Spread low→used |
|---|---|---|---|---|---|
| od_ts808 | gain_1k_db | 13.85 | 13.85 | 13.85 | 0 % |
| | thd_pct | 10.13 | 10.70 | 10.89 | +7.5 % |
| | out_pk_v | 0.508 | 0.562 | 0.574 | **+13 %** |
| | even_odd | 0.0146 | 0.0150 | 0.0151 | +3 % |
| dist_distplus | gain_1k_db | 5.879 | 5.879 | 5.879 | 0 % |
| | thd_pct | 33.77 | 33.78 | 33.89 | +0.4 % |
| | out_pk_v | 0.144 | 0.153 | 0.154 | +7 % |
| | even_odd | 0.0599 | 0.0601 | 0.0601 | +0.3 % |

`gain_1k_db` is a small-signal measurement (the diodes barely conduct), so it does not depend on
the LED model. The uncertainty shows in the output level (up to 13 %) and THD (up to 7.5 %) of the
TS-808. A datasheet with a logarithmic current axis, or measured LED data (option (c)), would
remove it.

**For reporting (decision 2026-11-16, option (b) accepted as is):** TS-808 results with
`D_clip=led` carry roughly **±1 dB output-level uncertainty** (the +13 % spread in `out_pk_v` is
20·log10(1.13) ≈ 1.06 dB) and about ±7.5 % THD uncertainty from the LED extrapolation below
0.107 mA. Phase 3 should cite this when reporting LED-mode TS-808 results.

### `DGE` (1N34A): UNVALIDATED placeholder

- [TAI] is the only manufacturer datasheet found. It gives only a **maximum** forward voltage
  (1.0 V at 5 mA), maximum reverse leakage and typical junction capacitance (0.8 pF), with no
  I-V curve, so no fit was made (decision: option 4).
- `DGE` stays the placeholder in `smoke_models.lib`, labelled there as unvalidated.
  `dist_distplus/block.yaml` marks `D_clip: validated: {ge: false}`. Validate rejects it unless
  `run.allow_unvalidated_models: true` in `config.yaml` (default false, for manual experiments
  only), and the Planner's catalog does not offer it. **Phase 3 runs must exclude it** (keep the flag false).
- **Possible future source (not used):** the retailer Tubes and More lists its own measured
  forward voltages (about 338–450 mV) and a "Vf curves" image for new-old-stock 1N34A:
  https://www.tubesandmore.com/products/diode-1n34a-germanium. These are retailer measurements,
  not a datasheet; they would need to be recorded as such.

### Diode model notes

- ngspice simulates at 27 °C by default, and the fitted models are at Tnom = 25 °C. The
  2 °C difference lowers silicon VF by about 4 mV (roughly −2 mV/°C), negligible here.

## Op-amp pin order (important)

Our templates call each op-amp as `X… inp inn vcc vee out <name>`
(non-inverting input, inverting input, positive supply, negative supply, output).
Many vendor models use the same order (`+IN −IN V+ V− OUT`), but some do not. If a vendor
subcircuit has a different order or name, keep the vendor file unchanged and add a small wrapper
with our name and pin order, for example:

```spice
* wrapper: our pin order -> vendor pin order (check the vendor file's .subckt line!)
.subckt JRC4558_HALF inp inn vcc vee out
XU inp inn vcc vee out NJM4558_VENDOR_NAME
.ends
```

## Rules for model files (enforced by `pedal_agent/tools/simulate.py`)

- **Self-contained.** Model text is pasted into the netlist, and the safety filter rejects
  `.include`, `.inc`, `.lib`, `.shell`, `.system` and `.exec` anywhere. Vendor files that pull in
  other files must be merged by hand.
- **ngspice 41 syntax.** PSpice-only constructs (some `VALUE={…}` / `TABLE` sources, special
  functions) may need translating. Every file is checked by simulating it before use.
- **Licence.** This repository is public. Only commit model files whose licence allows
  redistribution. Otherwise keep them out of git and note the download source here (like the
  "link only" rule for the GGG schematics).

## How they plug in

- The Checker reads one model file: `models/smoke_models.lib`, or the file named by the `MODELS`
  environment variable. The plan is a new `models/real_models.lib` containing all models above
  (plus wrappers), then a switch of the default.
- After the switch:
  1. `python -m tests.smoke_block`: DC checks for every block and choice
  2. `python -m pytest -q tests/test_checker.py`: some thresholds may need re-checking
     against the real models
  3. `python -m scripts.fill_typical_metrics`: re-measure `typical_metrics`
  4. Update the fake-run script targets if the TS-808 numbers moved
     (`pedal_agent/llm.py`, `default_fake_script`)
