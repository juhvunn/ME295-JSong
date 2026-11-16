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
| `JRC4558_HALF` | NJM/JRC4558 (one half of the dual op-amp) | `.subckt` | `inp inn vcc vee out` | od_ts808 (IC1a, IC1b) | Manufacturer SPICE model (Nisshinbo/NJR, NJM4558) | needed |
| `LM741` | LM741 / µA741 | `.subckt` | `inp inn vcc vee out` | dist_distplus | Manufacturer SPICE model (TI LM741 / µA741). Slew rate (~0.5 V/µs) matters for this pedal | needed |
| `Q2N4401` | 2N4401 NPN | `.model … NPN` | standard `C B E` | od_ts808 (input/output buffers) | Manufacturer model (e.g. onsemi) | needed |
| `Q2N3904` | 2N3904 NPN | `.model … NPN` | standard `C B E` | fuzz_ff_si (`Q_model` choice) | Manufacturer model (e.g. onsemi) | needed |
| `QBC109C` | BC109C NPN | `.model … NPN` | standard `C B E` | fuzz_ff_si (`Q_model` choice) | Legacy Philips/NXP library, or a BC549C model as a modern equivalent (say which) | needed |
| `D1N914` | 1N914 / 1N4148 silicon diode | `.model … D` | standard `A K` | od_ts808, dist_distplus (`D_clip=si`) | Manufacturer model (e.g. onsemi, Vishay) | needed |
| `DGE` | Germanium diode (1N270 in the original MXR; 1N34A is common) | `.model … D` | standard `A K` | dist_distplus (`D_clip=ge`) | No vendor models in practice: a published community model or a fit to datasheet I-V points (say which) | needed |
| `DLED_RED` | Red 3 mm/5 mm LED | `.model … D` | standard `A K` | od_ts808, dist_distplus (`D_clip=led`) | Usually fitted to datasheet I-V points (Vf ≈ 1.8 V at a few mA) | needed |

`fuzz_ff_si` has no `models:` entry: the transistor model *is* the `Q_model` choice
(`Q2N3904` or `QBC109C`).

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
