# Phase 3 groundwork: benchmark set, non-AI baselines, runner

Status: **approved with changes** (2026-11-16; decisions at the end). No API calls needed.
Goal: compare planners on the same fixed targets with the same Checker, budget and RunRecord
format. This answers the research question in CLAUDE.md: does changing topology reach more specs
than searching parameters of a fixed topology, under equal simulation budgets?

## 1. Benchmark set `benchmarks/v1.yaml`

**What it contains.** A fixed list of approved `TargetSpec`s (no Tone Analyst involved), each with
an id, a category and a short label. The hidden solutions go in a separate file,
`benchmarks/v1_solutions.yaml`, for analysis only. No planner or baseline may read it, and a test
enforces this.

**Generation** (`scripts/make_benchmarks.py --version v1 --seed <S>`, deterministic):
1. **Draw a random design** from the catalog, using validated choices only (`D_clip=ge` excluded):
   - Chain of 1 or 2 blocks, no block twice; `fuzz_ff_si` first if present (its `prefers_first`).
   - **Sampling distribution: the generator's own, different from the baselines' (section 4b (a)).**
     Knobs arcsine over [0, 1], default choice 25 %, parts log-uniform then E-series snapped.
2. **Simulate it with the real model set.** Keep it only if all DC checks pass and there are no errors.
3. **Pick 3–4 metrics and set ranges around the measured values,** so the drawn design is a known solution.
   **Use only metrics that actually vary on the solution's chain.** For each chain, 30 random
   settings are simulated (shared with the classification samples). A metric is eligible for that
   chain only if its 10–90 % spread across those samples is at least **twice the width of its
   tolerance window** (e.g. `ac_peak_hz` barely moves within `dist_distplus` or `fuzz_ff_si`, because
   the pickup resonance sets the peak). The spread of every metric for every chain is reported, and
   used for review. Windows:

   | Metric | Range around measured value m |
   |---|---|
   | gain_1k_db, ac_peak_db | m ± 1.5 dB |
   | thd_pct, ac_peak_hz | m ÷ 1.25 … m × 1.25 |
   | out_pk_v | m ÷ 1.2 … m × 1.2 |
   | even_odd | m ÷ 1.5 … m × 1.5, widened to at least ±0.02 (symmetric clipping gives values near 0) |

4. **Check the solution passes its own spec,** by re-simulating it (sims are deterministic).
   **Exclude targets that `od_ts808` at its defaults already passes:** every method would solve them
   at simulation 1, so they carry no information. The number of candidates excluded for this reason
   is recorded with the set.
5. **Classify the target empirically,** relative to the **start chain `[od_ts808]`** (P1). The evidence
   counts (samples run, samples passing) are recorded **per target**:
   - **A: start-chain reachable:** the solution is the start chain, or at least one of 100 random
     settings of the start chain passes.
   - **B: needs another single block:** solution is a different single block, and **0 of 100**
     random settings of the start chain pass.
   - **C: needs a 2-block chain:** solution is a 2-block chain, and **every single-block chain fails:
     0 of 100** random settings each for `od_ts808`, `dist_distplus` and `fuzz_ff_si`.
   - **D: likely unreachable:** a target outside what the catalog produces (e.g. high gain with
     very low THD, a peak far outside the measured range). Built by hand-perturbing generated
     targets, and checked with 500 random catalog samples that never pass. Labelled "likely", since
     this is evidence, not proof.
6. **Size:** 30 targets: **A 7, B 9, C 10, D 4**, drawn until each category is filled.

**Recorded with the set:**
- seed, generator version (git commit)
- model-set files and their SHA-256 (from the provenance code)
- sampling ranges and tolerance rules
- the number of start-chain and catalog samples behind each classification

A new model or catalog change means a new version (`v2`), never an edit of `v1`.

**Cost of generation:** about 7 × 100 (A) + 9 × 100 (B) + 10 × 300 (C) + 4 × 500 (D), plus the
metric-spread samples: roughly 7000 simulations, or 1 hour at about 0.5 s each. It runs once per
version, offline.

## 2. Non-AI baselines

Both baselines use the **same pipeline as the agent**: Validate → Checker → Router → RunRecord. A
deterministic "planner" stands in for the LLM. That gives the same budget accounting (12 Checker
simulations; rejected and duplicate proposals are free), the same stop rules (P2), the same step
format, and the same dashboard view. `model_id = "none"`, and `seed` is recorded.

**Common start (P1).** In benchmark runs **every method starts from `[od_ts808]` at its defaults.**
The first step simulates that chain and counts as 1 of the 12 simulations. It is recorded as
`initial_chain` with the title "Benchmark start: od_ts808 (defaults)". Each method continues from
there. For the agent's `baseline_fixed_topology` this **overrides decision C** (free choice of the
first chain) in benchmark runs only: its chain stays `[od_ts808]`. A free-start experiment can be
added later as a separate variant.

| Mode name (`RunRecord.mode`) | What it proposes after the common start |
|---|---|
| `agent` | LLM Planner, free topology (existing) |
| `baseline_fixed_topology` | LLM Planner, parameters of `[od_ts808]` only (existing; start fixed in benchmarks) |
| `random_catalog` (new, a) | Random chain of 1–2 blocks and random parameters each step, validated choices only, same sampling rules as the benchmark generator |
| `random_fixed_topology` (new, b) | Random parameters of `[od_ts808]`. Random rather than grid search: with 12 simulations and 4–6 parameters per block, a grid would have fewer than 2 values per parameter. |
| `random_fixed_topology_oracle` (new, P1) | Random parameters of **the solution's own chain**, starting from that chain at its defaults. An **upper-bound reference**: it is the only method allowed to read the hidden solution, and only its chain; this exemption is explicit in the no-peeking test. |

**Schema changes:**
- `RunRecord.mode`: three new values (the two baselines and the oracle).
- New optional fields: `seed: int`, and `benchmark: {set, target_id, category}`. The hidden solution
  is never copied into the RunRecord.

**Benchmark runs skip the Tone Analyst.** A run created with an already-approved spec starts directly
with the common start step. Step 1 is then a `human_approve_spec` step marked "benchmark spec (pre-approved)".

**Stop rules in benchmark runs (P2):** `all_pass` and `budget` only. Stall and duplicate stops are
off, for all methods. The **Planner-call cap (2 × sim budget = 24 calls) stays on**, as the cost
safety net. Outside benchmarks the normal rules apply.

## 3. Runner `scripts/run_benchmark.py`

```
python -m scripts.run_benchmark --set v1 --methods random_catalog random_fixed_topology agent:fake \
       --repeats 5 --seed 1 [--targets T01,T07] [--out runs/bench/<timestamp>]
```
- **Every (method, target, repeat) is one run,** with seed = hash(base seed, method, target, repeat),
  written as `runs/bench/<timestamp>/<run_id>.json` (gitignored).
- **Methods:** `random_catalog`, `random_fixed_topology`, `agent:fake`, and later `agent:real` and
  `baseline_fixed_topology:real`. The real ones need the API key, and ask before spending money.
- **Summary** (`summary.md` + `summary.csv`), per method and per category A/B/C/D:

  | Column | Definition |
  |---|---|
  | success rate | share of runs ending `all_pass` (A–C); for D, share stopped by budget/stall without false success |
  | sims used | median and IQR, all runs and successful runs |
  | best score | median of the best `CheckReport.score` (0 = all targets pass) |
  | topology changes | mean `RunRecord.topology_changes` |
  | wall time | median seconds per run |
  | flagged | number of runs with `placeholder_or_unvalidated = true` (must be 0) |

  Plus a per-target table (success count per method), so it's visible *which* targets need topology changes.
- **Plot:** cumulative success rate vs number of simulations used (1–12), one line per method,
  overall and per category A/B/C. Saved as `success_vs_sims.png`, with the underlying numbers in
  `success_vs_sims.csv`.

**Rough run time** for the non-AI methods: 30 targets × 12 sims × 5 repeats × 3 methods = 5400 sims,
about 45–90 minutes. Option: `--workers N` (parallel ngspice processes) later if needed.

**Agent runs (P3)** use a **stratified subset**, e.g. 12 targets (proportional to A/B/C/D) × 3 repeats.
The exact numbers are decided when an API budget is set. The runner then reports an **estimated
cost per agent mode** before starting, computed from the *measured* cost of a real run (tokens ×
config prices, from `RunRecord.cost_usd`) × targets × repeats. It has no estimate until a real
run exists.

## 4. Tests (no API cost)

- **Benchmark file:** loads into `TargetSpec`s; ids unique; only validated choices in the solutions;
  versioned header complete (seed, commit, model hashes).
- **Solutions pass:** a sample of 3 targets (one each of A/B/C) re-simulated; their solution passes.
  The full check is a script, not a test, to keep the suite fast.
- **No peeking:** the baselines, the agent and the runner never open `*_solutions.yaml` (test by
  patching file access during a run). The single explicit exemption is
  `random_fixed_topology_oracle`, which reads only the solution's chain.
- **Common start:** every method's first simulated step is `[od_ts808]` at its defaults, except the
  oracle, which starts at the solution's chain.
- **Benchmark stop rules:** stall and duplicate off, Planner-call cap on.
- **Baselines:**
  - same seed → identical RunRecord candidates; budget respected (≤ 12 sims)
  - `random_fixed_topology` never changes the chain; `random_catalog` uses only validated choices
  - mode names, `seed` and `model_id = "none"` recorded
- **Pre-approved spec path:** a benchmark run starts with the common start step, without the Tone Analyst.
- **Classification evidence:** every target in `v1` carries its sample counts (and the metric-spread
  table exists for every chain used).
- **Runner end to end with `agent:fake`** plus both baselines, on 2 targets × 1 repeat: RunRecords
  validate, and the summary table has the expected rows and columns.

## 4b. Fairness: generator vs random baselines (proposal, 2026-11-16)

**Problem.** If the generator draws solutions from the same distribution the random baselines
search, the benchmark is tailored to them: targets are made exactly the way they search.

**Decision (approved 2026-11-16): do both (a) and (b).**

**(a) Generate solutions from a different distribution than the baselines search.**

| | Random baselines (unchanged) | Benchmark generator (new) |
|---|---|---|
| Knobs | uniform in [0.05, 0.95] | **full [0, 1], arcsine (Beta(0.5, 0.5)) distribution**: more weight near the ends, where real settings often sit (drive full up, tone down). About 29 % of generator knob values fall outside the baselines' range. |
| Choices (D_clip, Q_model) | uniform over validated choices | **default choice 25 %**, the other validated choices share 75 % (e.g. od_ts808: si 25 %, led 37.5 %, none 37.5 %) |
| Parts (E-series) | uniform over the E-series values in range | log-uniform over [min, max], then snapped to the E-series |
| Chain | 1–2 blocks, uniform | set by the category quotas (A/B single block, C 2-block) |

The **classification samples** (100 per start chain, 100 per single block, 500 catalog) use the
generator's wider distribution. So "0 of 100 pass" is evidence against a broader search than the
baselines run.

**(b) Add 6 hand-written, musically motivated targets.** They are numeric specs, written down and
committed **before** any search on them, and classified with the same A–D evidence rules. Their
solutions are unknown in advance, so the evidence order is:
- **A:** a start-chain sample passes.
- **B:** a sample of another single block passes, and the start chain fails.
- **C:** all single blocks fail, and a sample from 300 random 2-block chains passes.
- **D:** none of 500 catalog samples pass.

The solution found is stored like the generated ones. Approved targets (numbers are musical
judgment, approved 2026-11-16 with H5 raised from ≥ 0.5 to ≥ 0.8, because the fuzz default already
gives about 0.58). They are stored in `benchmarks/v1_hand_targets.yaml` and **committed before any
search runs on them. They are never changed after results are seen; any change means a new version.**

| Id | Idea | Targets |
|---|---|---|
| H1 | rougher than a TS-808, less than a fuzz | thd_pct 15–30, gain_1k_db ≥ 10, ac_peak_hz 600–1200 |
| H2 | clean boost | thd_pct ≤ 2, gain_1k_db ≥ 12 |
| H3 | bright, raw distortion | thd_pct ≥ 25, ac_peak_hz ≥ 2000 |
| H4 | dark, smooth overdrive | thd_pct 3–10, ac_peak_hz ≤ 700 |
| H5 | asymmetric, gated fuzz | even_odd ≥ 0.8, thd_pct ≥ 30 |
| H6 | fuzz into overdrive, mid-forward | even_odd ≥ 0.3, thd_pct ≥ 15, ac_peak_hz 500–1200 |

**Note on H2:** a clean boost may well be **unreachable** with this library at the 300 mV test
level. Every block clips at that level, and none has a clean-boost mode with enough headroom. It is
kept anyway: "no clean boost in the library" is a valid finding (it would land in category D).

**Size and cost.** The set becomes 30 generated targets (A 7, B 9, C 10, D 4) **+ 6 hand-written** = 36.
Hand-written targets are reported **both within their A–D category and separately** (field
`source: generated | hand`). Their classification costs at most about 1100 simulations each (about 1 h
for all six, at the outside), on top of the roughly 1 hour for the generated set.

**Remaining bias (limitations to state in Phase 3 results).**
1. **Same design space.** Solutions still come from the catalog `random_catalog` searches. The
   distribution mismatch reduces its advantage but does not remove it.
2. **Categories are defined by random sampling of the start chain.** B and C are, by construction,
   targets that 100 random start-chain samples miss, so `random_fixed_topology` (12 samples) is
   *expected* to fail them. The informative comparisons on B/C are agent vs `random_catalog`, agent vs
   `baseline_fixed_topology` (LLM), and all vs the oracle (upper bound).
3. **Generated targets are "random-design-shaped":** combinations of metric windows a random design
   happens to produce, not necessarily musically meaningful. The hand-written targets address this,
   but they are few and reflect one person's judgment.
4. **Same tolerance windows and metric definitions for all methods,** measured with fitted models;
   `fuzz_ff_si` results carry the sensitivity ranges in `models/README.md`.

## 5. Order of work

Each step ends with its tests, a short report and your OK before committing.
1. Schema additions (modes, `seed`, `benchmark`), plus the pre-approved spec path, the common start
   step and the benchmark stop rules in the graph
2. Deterministic planners for the two baselines
3. Benchmark generator; generate `v1`, then you review the targets and categories before anything is committed
4. Runner and summary table; a first non-AI run on `v1`
5. Fake-LLM end-to-end tests

## Decisions (approved 2026-11-16)

- **P1. Common start `[od_ts808]`** for **all** methods in benchmarks: the AI-free baselines, the agent,
  and `baseline_fixed_topology` (overriding decision C for benchmark runs only). Categories A–D are
  defined relative to it. A free-start experiment may follow as a separate variant. The oracle variant
  (`random_fixed_topology_oracle`) is included.
- **P2. Benchmark stop rules:** `all_pass` and `budget` only (stall and duplicate off) for all methods.
  The Planner-call cap (2 × sims) stays on, as the cost safety net.
- **P3. Size:** 30 targets, **A 7, B 9, C 10, D 4**; chains of 1–2 blocks. Agent runs use a stratified
  subset (e.g. 12 targets × 3 repeats), decided once there is an API budget, with an estimated cost
  per agent mode based on the measured cost of a real run.
- **P4. Tolerances** as in the table above, 3–4 metrics per target, and **only metrics that vary on
  the solution's chain** (10–90 % spread ≥ 2 × the window width; spreads reported).
- **P5. Mode names:** `random_catalog`, `random_fixed_topology`, `random_fixed_topology_oracle`
  (keeping `agent` and `baseline_fixed_topology`).
- **Classification evidence:** C requires every single-block chain to fail (0 of 100 each); B requires
  the start chain to fail (0 of 100). Evidence counts are recorded per target.

**Out of scope here:** CLAUDE.md baselines 1 and 2 (single LLM, one candidate; single LLM with the
same tools). They need the API, and follow once the real-run test has been done.
