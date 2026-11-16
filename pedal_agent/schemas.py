"""Data contract between the agent backend and the dashboard.

Every panel of the dashboard is rendered from a RunRecord (plus the block
library). The backend writes one RunRecord JSON per run to runs/<run_id>.json;
the dashboard only reads these files and never calls the agent directly
except through the actions listed in DASHBOARD_SPEC.md.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, computed_field

# A failed simulation has score = inf (and metrics may be inf/nan). Plain JSON has no infinity, so these are
# written as the strings "Infinity" / "NaN" and read back as floats (otherwise inf became null and the run
# record could not be reloaded).
FLOAT_JSON = ConfigDict(ser_json_inf_nan="strings")


def now() -> datetime:
    return datetime.now(timezone.utc)


# ---------- Target spec (Tone Analyst output, approved by the human) ----------
MetricName = Literal["gain_1k_db", "thd_pct", "ac_peak_hz", "ac_peak_db",
                     "even_odd", "out_pk_v"]

class MetricTarget(BaseModel):
    name: MetricName
    lo: Optional[float] = None          # None = unbounded
    hi: Optional[float] = None
    unit: str = ""
    label: str                          # human-readable, shown in the table
    weight: float = 1.0

class TargetSpec(BaseModel):
    goal_text: str
    genre: Optional[str] = None
    reference: Optional[str] = None
    targets: list[MetricTarget]
    test_signal: dict = Field(default_factory=lambda: {"f0_hz": 1000.0, "amp_v": 0.3})
    approved: bool = False
    approved_at: Optional[datetime] = None


# ---------- Design candidate (Planner output) ----------
class BlockInstance(BaseModel):
    block_id: str                       # must exist in library/blocks
    params: dict[str, float | str] = Field(default_factory=dict)  # overrides of block.yaml defaults

class Candidate(BaseModel):
    chain: list[BlockInstance]          # signal order, pickup -> ... -> amp
    rationale: str


# ---------- Tone Analyst LLM output ----------
class ToneDraft(BaseModel):
    """What the LLM returns; code wraps it in a TargetSpec (test signal, approval fields)."""
    targets: list[MetricTarget]
    rationale: str                      # why these targets fit the goal (Design choices panel)


# ---------- Planner LLM output ----------
# Structured outputs cannot express free-form dicts, so the LLM returns params
# as name/value pairs; to_candidate() converts them into BlockInstance.
PlannerAction = Literal["initial_chain", "adjust_params", "swap_block", "add_block", "remove_block"]

class ParamValue(BaseModel):
    name: str
    value: float | str

class ProposedBlock(BaseModel):
    block_id: str
    params: list[ParamValue] = Field(default_factory=list)

class PlannerDecision(BaseModel):
    action: PlannerAction
    chain: list[ProposedBlock]          # the full proposed chain, pickup -> amp
    rationale: str

    def to_candidate(self) -> Candidate:
        return Candidate(chain=[BlockInstance(block_id=b.block_id, params={p.name: p.value for p in b.params})
                                for b in self.chain], rationale=self.rationale)


# ---------- LLM usage (cost accounting) ----------
class LLMUsage(BaseModel):
    node: Literal["tone_analyst", "planner"]
    model_id: str
    effort: str
    input_tokens: int
    output_tokens: int
    attempts: int = 1                   # 2 after a retry; tokens are summed over attempts


# ---------- Checker output ----------
class MetricResult(BaseModel):
    model_config = FLOAT_JSON
    name: MetricName
    value: float
    status: Literal["pass", "low", "high"]

class Plots(BaseModel):
    """Downsampled data for the Test result panel."""
    t_s: list[float]
    v_in: list[float]
    v_out: list[float]
    freq_hz: list[float]
    mag_db: list[float]

class ModelFile(BaseModel):
    """A part-model library file used by a simulation (see models/manifest.yaml)."""
    path: str                           # relative to the repo root when inside it
    sha256: str                         # of the text with LF line endings
    status: Literal["validated", "placeholder", "unregistered"]

class CheckReport(BaseModel):
    model_config = FLOAT_JSON
    metrics: dict[str, float]
    results: list[MetricResult]
    score: float                        # weighted normalized error, 0 = all pass
    dc_ok: bool
    errors: list[str] = Field(default_factory=list)   # validate / ngspice failures
    netlist_sha256: Optional[str] = None
    plots: Optional[Plots] = None
    model_files: list[ModelFile] = Field(default_factory=list)
    unvalidated_choices: list[str] = Field(default_factory=list)   # e.g. "dist_distplus.D_clip=ge"
    # True if any model file is not "validated" or any unvalidated choice was used;
    # None for reports written before this was recorded
    placeholder_or_unvalidated: Optional[bool] = None

    @property
    def n_pass(self) -> int:
        return sum(r.status == "pass" for r in self.results)


# ---------- Run history (Design choices panel) ----------
Action = Literal["tone_analyst", "human_approve_spec", "initial_chain", "adjust_params",
                 "swap_block", "add_block", "remove_block", "human_feedback",
                 "human_accept", "stop"]

class Step(BaseModel):
    n: int
    agent: Literal["tone_analyst", "planner", "human", "router"]
    action: Action
    title: str                          # short line shown in the panel
    why: str                            # rationale / feedback text
    candidate: Optional[Candidate] = None
    report: Optional[CheckReport] = None
    validation_errors: list[str] = Field(default_factory=list)   # candidate rejected, no sim used
    warnings: list[str] = Field(default_factory=list)            # e.g. E-series snapping, chain order
    duplicate_of: Optional[int] = None  # Step.n of an identical, already checked candidate (sim skipped)
    llm: Optional[LLMUsage] = None
    at: datetime = Field(default_factory=now)


TOPOLOGY_ACTIONS = {"swap_block", "add_block", "remove_block"}

Mode = Literal["agent", "baseline_fixed_topology", "random_catalog", "random_fixed_topology",
               "random_fixed_topology_oracle"]

class BenchmarkRef(BaseModel):
    """Benchmark target a run belongs to (docs/phase3_plan.md). The hidden solution is never
    stored here; only the oracle's start chain is the solution's chain (at defaults)."""
    set: str                            # e.g. "v1"
    target_id: str
    category: Literal["A", "B", "C", "D"]
    start_chain: list[BlockInstance]    # simulated as the first step: [od_ts808] defaults (oracle: solution chain)

class RunRecord(BaseModel):
    run_id: str
    project_id: str
    model_id: str                       # pinned, e.g. "claude-opus-5-5"
    effort: str                         # pinned effort level
    mode: Mode = "agent"
    seed: Optional[int] = None          # for the random baselines (and repeat bookkeeping)
    benchmark: Optional[BenchmarkRef] = None   # set for benchmark runs: pre-approved spec, common start, benchmark stop rules
    created_at: datetime = Field(default_factory=now)
    status: Literal["awaiting_spec_approval", "running", "awaiting_feedback",
                    "accepted", "stopped"]
    stop_reason: Optional[Literal["all_pass", "budget", "stall", "duplicate",
                                  "human_review", "human_accept", "error", "infra_error"]] = None
    # "error": the LLM gave no valid output after its retries (a method outcome, counts as a failure).
    # "infra_error": an exception outside the method (e.g. a file-save failure); benchmark runs that end
    # this way are re-run and left out of results. Simulation timeouts and ngspice failures are neither:
    # they are normal Checker reports that use budget.
    spec: Optional[TargetSpec] = None
    steps: list[Step] = Field(default_factory=list)
    best_step: Optional[int] = None     # Step.n with the lowest score
    sims_used: int = 0
    sim_budget: int = 12
    price_in_per_mtok: float = 0.0      # USD per million tokens, copied from config.yaml at run start
    price_out_per_mtok: float = 0.0
    audio: Optional[dict] = None        # {"clip": ..., "dry": path, "processed": path}

    @computed_field
    @property
    def placeholder_or_unvalidated(self) -> Optional[bool]:
        """True if any check in this run used a placeholder/unregistered model file or an
        unvalidated choice. Such runs must not be used for reported results."""
        flags = [s.report.placeholder_or_unvalidated for s in self.steps
                 if s.report and s.report.placeholder_or_unvalidated is not None]
        return any(flags) if flags else None

    @computed_field
    @property
    def model_files(self) -> list[ModelFile]:
        """Distinct model files (path, SHA-256, status) used by the checks in this run."""
        seen = {}
        for s in self.steps:
            for f in (s.report.model_files if s.report else []):
                seen[(f.path, f.sha256)] = f
        return list(seen.values())

    @property
    def input_tokens(self) -> int:
        return sum(s.llm.input_tokens for s in self.steps if s.llm)

    @property
    def output_tokens(self) -> int:
        return sum(s.llm.output_tokens for s in self.steps if s.llm)

    @property
    def cost_usd(self) -> float:
        return (self.input_tokens * self.price_in_per_mtok + self.output_tokens * self.price_out_per_mtok) / 1e6

    @property
    def topology_changes(self) -> int:
        """Simulated candidates whose chain changed blocks (rejected/duplicate proposals excluded)."""
        return sum(s.action in TOPOLOGY_ACTIONS and s.report is not None for s in self.steps)

    @property
    def best(self) -> Optional[Step]:
        return next((s for s in self.steps if s.n == self.best_step), None)


class Project(BaseModel):
    project_id: str
    name: str
    genre: Optional[str] = None
    describe: str = ""
    reference: Optional[str] = None
    run_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now)
