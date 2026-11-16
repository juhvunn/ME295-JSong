# Plan: replacing the placeholder part models

Status: **draft for approval** (2026-11-16). No model code is written yet.
Goal: replace every model in `models/smoke_models.lib` (see `models/README.md`) with models we
can justify part by part, validate them against datasheets, then re-measure the pedal blocks.

All numbers, URLs and licence terms below that say **"to read"** or **"to verify"** are not filled
in yet on purpose. They will come from the actual documents, and each one will be cited in
`models/README.md`.

## Overview

| Part (netlist name) | Approach | Committed? | Validation |
|---|---|---|---|
| `JRC4558_HALF`, `LM741` | **A1** our own behavioural op-amp macromodel, datasheet values | yes (ours) | GBW, slew rate, swing, gain |
| `D1N914`, `DGE`, `DLED_RED` | **A2** fit `Is, N, Rs` to datasheet I-V points | yes (ours) | reproduces the points |
| `Q2N4401`, `Q2N3904`, `QBC109C` | **B** manufacturer models | only if the licence clearly allows it; otherwise downloaded at setup | runs in ngspice 41; hFE at 1 mA |

Steps A1, A2 and B are independent of each other. C (validation tests) is written alongside each
one, and D (re-measuring the blocks) needs all three.

## A1. Behavioural op-amp macromodel (ours)

**One parameterised subcircuit**, `models/opamp_macro.lib`:

```
.subckt OPAMP_MACRO inp inn vcc vee out
+ params: AOL=… GBW=… SR=… VOH_DROP=… VOL_DROP=… IB=… ROUT=… RIN=…
```

Structure (classic single-pole, slew-limited macromodel):
1. **Input stage:** `RIN` between the inputs. `IB` bias current sources into each input to ground.
2. **Transconductance with a current clamp:** `I = clamp(gm·(Vinp − Vinn), ±Imax)` into an
   integrating capacitor `C`. The slew rate is `SR = Imax / C`, the unity-gain frequency is
   `GBW = gm / (2π·C)`, and a shunt `R` gives the DC open-loop gain `AOL = gm·R`. All three come
   straight from datasheet values.
3. **Output stage:** a buffered output, limited smoothly between `V(vee) + VOL_DROP` and
   `V(vcc) − VOH_DROP`, through `ROUT`.
4. **Not modelled** (stated in the README): input offset, common-mode range limits, noise, supply
   current, second poles. Our circuits bias the inputs at Vcc/2, well inside the common-mode range.

**Thin wrappers** with our names and the datasheet values:
```
.subckt JRC4558_HALF inp inn vcc vee out
X1 inp inn vcc vee out OPAMP_MACRO AOL=… GBW=… SR=… …
.ends
.subckt LM741 inp inn vcc vee out
X1 inp inn vcc vee out OPAMP_MACRO AOL=… GBW=… SR=… …
.ends
```

**Values to read** (typical values, with the datasheet name, revision and page/table cited in
`models/README.md`):

| Param | JRC4558 (NJM4558 datasheet) | LM741 (TI LM741 datasheet) | Note |
|---|---|---|---|
| AOL | to read | to read | open-loop voltage gain |
| GBW | to read | to read | gain-bandwidth / unity-gain frequency |
| SR | to read | to read | **critical for LM741 in dist_distplus** |
| VOH_DROP / VOL_DROP | to derive | to derive | from output-swing specs; see the open question below |
| IB | to read | to read | input bias current |
| ROUT | to read or estimate | to read or estimate | open-loop output resistance; often not specified |

**Open question (supply).** Datasheets give output swing at ±15 V (sometimes ±5 V or ±9 V)
into 2 kΩ or 10 kΩ. Our pedals run on a single 9 V supply. Proposal: use the drop from the rail
at the supply and load closest to ours, and state that assumption in the README.

## A2. Diode fits (ours)

`scripts/fit_diodes.py` plus `models/diode_points.yaml`. For each diode, the YAML holds:
- 4–8 forward `(I, V)` points read from the datasheet's forward-characteristic curve or table,
  spread over the range our circuits use (about 10 µA to 10 mA)
- the source: datasheet name, revision, figure/table, and "read from the graph" or "from the table"
- `Cjo` and `TT` from the datasheet when they are given (the fit is DC-only)

The script fits the Shockley diode with series resistance, `V = N·Vt·ln(I/Is + 1) + I·Rs`, by
least squares on the voltage error. It writes `models/diodes_fitted.lib` (a generated file,
committed) and prints the residuals.

| Model | Part / datasheet | To decide |
|---|---|---|
| `D1N914` | 1N914 or 1N4148 (manufacturer to choose) | which datasheet |
| `DGE` | 1N270 (original MXR) or 1N34A | which part. Germanium datasheets are often sparse, and the points may be few. |
| `DLED_RED` | a specific red LED part | **you choose the LED**; Vf depends strongly on the part |

New dependency: `scipy` (`optimize.least_squares`). The alternative is a small fit written with
numpy only; I recommend scipy, which is standard and well tested.

## B. Vendor transistor models

For each of `Q2N4401`, `Q2N3904` and `QBC109C`:
1. **Find** the manufacturer's SPICE model (onsemi, Diodes Inc., Central Semiconductor, NXP/Nexperia, …).
   `BC109C` is obsolete. If no manufacturer model exists, use a `BC549C` model as the modern equivalent
   and record that substitution explicitly.
2. **Read the terms** on the download page and in the file header. Record the URL, the date
   accessed and the exact licence wording in `models/README.md`.
3. **Decide:**
   - Redistribution clearly allowed → commit to `models/vendor/<part>.lib` with the source noted.
   - Not clearly allowed (the common case: copyright notice and no licence) → **do not commit**.
     Add `scripts/fetch_models.py` with the URL and a **SHA-256 checksum**. It downloads into
     `models/vendor/`, which is gitignored, and refuses files whose checksum differs. Tests that
     need the file **skip with a clear message**: `"Q2N3904 model missing: run python -m scripts.fetch_models"`.
4. **Check** that the file runs in ngspice 41 with no `.include`/`.lib` lines. Simple `.model … NPN(…)`
   lines are standard; parameters that ngspice doesn't know (e.g. `Vceo`, `Icrating`, `mfg`)
   are checked for warnings or errors. If a file is a `.subckt` with a different pin order or name,
   wrap it to our name with pins `C B E`.

Risk: vendor sites change URLs or block automated downloads. The checksum guarantees that
everyone simulates the identical file; if a download fails, the script prints the manual
download instructions.

## B2 (revised 2026-11-16, replaces B): our own fitted transistor models

**Why.** The licence check found no manufacturer transistor model that may be redistributed
(onsemi and Central site terms forbid copying without consent; Diodes Inc. refused automated
access), and no stable direct download URL. Decision: **B2**, our own Gummel-Poon models fitted
to datasheet curves, committed like A1/A2. An optional **B1** cross-check comes later: you
download one vendor model by hand into the gitignored `models/vendor/`, and we compare it with
ours without committing it.

**Scope: what matters in our circuits.** Measured by simulation (real op-amps, fitted diodes,
*placeholder* transistors; to be re-measured after the fit):

| Transistor | No signal | 300 mV, 1 kHz input |
|---|---|---|
| fuzz_ff_si Q1 (any fuzz setting) | 232 µA | 218–270 µA |
| fuzz_ff_si Q2 | 0.70 mA | cut off (<10 µA) for 33–47 % of the cycle, otherwise up to 0.98 mA |
| od_ts808 Q1/Q2 buffers (2N4401) | 313 µA | 267–360 µA |

So **10 µA–1 mA is the priority range**, with the exponential turn-on below 10 µA mattering for
fuzz Q2. Nothing runs above 1 mA. The fit covers 10 µA–10 mA where the datasheet has data; below
the lowest datasheet point is extrapolated and reported, as for the LED.

**Parts and datasheets** (typical curves preferred; URL, revision, page and SHA-256 recorded as in A1/A2):
- `Q2N3904`: onsemi 2N3904 datasheet
- `Q2N4401`: onsemi 2N4401 datasheet
- `QBC549C`: a BC549C datasheet with typical hFE-vs-Ic curves (onsemi BC549B/C if it has them,
  otherwise another manufacturer's); recorded as a **stand-in for the BC109C** (decision D4)

**What is fitted, what is taken, what is assumed** (Gummel-Poon `.model … NPN`, `Tnom=25`):

| Parameters | Source | Treatment |
|---|---|---|
| `IS`, `NF` | typical VBE(on) vs Ic curve | **fitted** (priority 10 µA–10 mA) |
| `BF`, `ISE`, `NE`, `IKF` | typical hFE vs Ic curve | **fitted** (low-current fall-off and high-current roll-off) |
| `CJE`, `CJC` (+ `MJE`/`MJC` defaults) | typical input/output capacitance (Cibo/Cobo) | taken from the table/figure, no fit |
| `TF` | typical fT at its stated Ic | derived: TF ≈ 1/(2π·fT) minus the capacitance contribution; checked loosely |
| `VAF` | only if a typical output characteristic or `hoe` is given; otherwise **assumed** (stated value) | listed as an assumption |
| `BR`, `NR`, `VAR`, `ISC`, `NC`, `IKR`, `RB`, `RE`, `RC`, temperature parameters | not supported by audio-band, forward-active use or by the datasheets | ngspice defaults or stated values, **listed as assumptions** |

**Validation tests** (`tests/test_models.py`):
- hFE at each fitted datasheet point within **±10 %**; VBE within **±10 mV**
- the datasheet hFE min–max at its spec current contains the model's value
- fT at the datasheet condition within ±25 % (a loose check, since no detailed fit is done)
- the model files pass the sandbox filter

**Sensitivity** (like the LED): **min-hFE and max-hFE variants** built from the datasheet hFE range
(BF scaled so that hFE at the spec current equals the datasheet min and max). With each variant:
- `fuzz_ff_si`, both `Q_model` choices: bias point (V(c1), V(c2)), gain_1k_db, thd_pct, even_odd, out_pk_v
- `od_ts808`: DC checks (vr, o1, o2) and the buffer emitter voltages

Results go in `models/README.md`, written so Phase 3 can cite them.

**Additions (approved 2026-11-16).**
- Fuzz Q2's cut-off below 10 µA is set mainly by the VBE-vs-current curve (`IS`, `NF`), not by hFE.
  Report the lowest current each datasheet VBE curve reaches. Record anything below it as
  extrapolated (like the LED), and add VBE-extrapolation variants to the sensitivity runs so they
  show how much the fuzz asymmetry (`even_odd`) depends on it.
- `VAF` at a stated default is acceptable: ro ≈ VAF/Ic is far above Q1's 33 kΩ collector load.
  Listed as an assumption.

**Rename (D4).** `QBC109C` → `QBC549C` everywhere: the `fuzz_ff_si` choice, with a stand-in note in
`block.yaml`; the placeholder in `smoke_models.lib`, renamed but still labelled placeholder;
`typical_metrics` keys; tests. The `QBC109C` name is not kept.

**Order.**
1. Download the datasheets, read the curves (vector digitizing as in A2), then show you the available data.
2. Fit the models, write the tests, rename.
3. Sensitivity runs; README section.
4. Your OK, then commit.

Then the plumbing step (`real_models.lib`, `models:` setting in `config.yaml`) and D (before/after table).

## How the models plug in

- New `models/real_models.lib` assembled from `opamp_macro.lib` + wrappers + `diodes_fitted.lib`
  + the transistor files, in a fixed order. `smoke_models.lib` stays for before/after comparisons.
- `config.yaml` gets a new `models:` setting (`real` or `smoke`). The Checker reads it, and the
  `MODELS` environment variable still overrides it.
- If `real` is selected but a downloaded vendor file is missing, the Checker stops with the same
  clear message (no silent fallback to placeholders).

## C. Validation tests (`tests/test_models.py`)

| Test | Method | Pass criterion |
|---|---|---|
| Op-amp GBW | non-inverting gain of 100, AC sweep, −3 dB frequency × 100 | within **±10 %** of the datasheet GBW |
| Op-amp slew rate | unity-gain follower, large input step, dV/dt between 10 % and 90 % | within **±10 %** of the datasheet SR |
| Op-amp DC gain and swing | open loop at a low frequency; output clipped on a 9 V single supply | AOL within ±1 dB; swing equals the modelled rail drops |
| Diode fit | ngspice DC sweep through each datasheet current | each datasheet voltage reproduced within **±20 mV**, or ±3 % for the LED (to confirm after the fit) |
| Transistor hFE | Ic = 1 mA, Vce = 5 V, DC operating point, hFE = Ic/Ib | inside the datasheet hFE range at (or nearest to) 1 mA |
| Sandbox | every model file passes `check_netlist` (no `.include`/`.lib`) | — |

The tolerances are proposals: ±10 % is tight enough to catch a wrong slew-rate implementation
(e.g. factor 2π errors) but allows for the macromodel's single pole.

## D. Re-measure the blocks

1. `python -m tests.smoke_block` and `pytest tests/test_checker.py` with the real models: DC checks
   for every block and choice.
2. New `scripts/compare_models.py`: runs each block at its defaults, once per choice, with
   **smoke** and with **real** models. It prints a before/after table (gain, THD, peak frequency,
   even/odd, output peak, DC check) **without** changing any `block.yaml`.
3. After you approve the table: switch the default to `real` and rerun
   `scripts/fill_typical_metrics.py`.
4. **Expected knock-on fixes.** The checker test thresholds and the fake-run script (`default_fake_script`,
   which expects TS-808 at drive 0.7 to pass) may need updating if the numbers move. Each such
   change will be shown to you, not silently adjusted.

## Order of work (each step: tests, short report, your OK before committing)

1. A1 op-amp macromodel + datasheet values + GBW/SR/swing tests
2. A2 diode points + fit script + fitted models + diode tests
3. B transistor sourcing: a licence decision per part (shown to you before any download or commit),
   then the files or the fetch script + hFE tests
4. Plumbing: `real_models.lib`, `config.yaml` `models:` setting, Checker switch
5. D before/after comparison table → your approval → `typical_metrics` re-measured, knock-on fixes

## Decisions for you

- **D1. Datasheets.** Which manufacturer's datasheet for each part (e.g. NJM4558 vs RC4558, TI LM741
  vs µA741; for the diodes, which 1N914/1N4148). You said you'll bring the files; I'll read the
  values from them.
- **D2. Red LED.** Which LED part to model (its datasheet I-V curve).
- **D3. Germanium diode.** 1N270 (the original MXR) or 1N34A (easier to find data for).
- **D4. BC109C.** If no manufacturer model exists, is a BC549C model acceptable as a stand-in (recorded as such)?
- **D5. scipy** as a new dependency for the diode fit (recommended).
- **D6. Single 9 V supply assumption** for the op-amp output swing, as described above.

## Decisions (approved 2026-11-16)

- **D1.** NJM4558 (Nisshinbo/JRC; GGG's schematic says JRC4558D), TI LM741, and one manufacturer datasheet
  covering both 1N914 and 1N4148. Datasheets are downloaded from the manufacturers' sites; URL, document
  version and page are recorded for every value.
- **D2.** A common 5 mm red LED whose datasheet has an I-V curve, including its lowest-current points.
  Anything below the lowest datasheet point is recorded as extrapolated (clipping happens at µA–mA).
- **D3.** 1N34A, recorded as a stand-in for the original MXR's 1N270.
- **D4.** BC549C as a stand-in for BC109C. The `Q_model` choice is renamed to `QBC549C` (no `QBC109C`
  name kept), and the stand-in is noted in `fuzz_ff_si/block.yaml`.
- **D5.** scipy is added for the diode fit.
- **D6.** Use a "maximum output voltage vs supply voltage" graph if a datasheet has one; otherwise
  assume constant headroom from the rails and state that in `models/README.md`.
