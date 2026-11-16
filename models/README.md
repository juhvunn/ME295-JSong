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
| `D1N914` | 1N914 / 1N4148 silicon diode | `.model … D` | standard `A K` | od_ts808, dist_distplus (`D_clip=si`) | Manufacturer model (e.g. onsemi, Vishay) | needed |
| `DGE` | Germanium diode (1N270 in the original MXR; 1N34A is common) | `.model … D` | standard `A K` | dist_distplus (`D_clip=ge`) | No vendor models in practice: a published community model or a fit to datasheet I-V points (say which) | needed |
| `DLED_RED` | Red 3 mm/5 mm LED | `.model … D` | standard `A K` | od_ts808, dist_distplus (`D_clip=led`) | Usually fitted to datasheet I-V points (Vf ≈ 1.8 V at a few mA) | needed |

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
