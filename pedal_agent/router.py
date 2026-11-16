"""Router: deterministic stop/continue decision from the RunRecord.

Called after every Planner attempt (checked, invalid, or duplicate). Rules, in order:
  all_pass   the latest check passes every target (DC checks OK, no errors)
  budget     sims_used >= sim_budget, or the Planner-call safety net is reached
  stall      the best score has not improved in the last `stall_checks` checks
  duplicate  the last two Planner proposals were both duplicates of earlier candidates
"""
from dataclasses import dataclass

from pedal_agent.config import load_config
from pedal_agent.schemas import Candidate, RunRecord, Step
from pedal_agent.validate import fingerprint


@dataclass
class RouterConfig:
    sim_budget: int = 12
    stall_checks: int = 3
    max_planner_calls: int = 24

    @classmethod
    def from_config(cls, cfg: dict | None = None) -> "RouterConfig":
        run = (cfg or load_config())["run"]
        return cls(run["sim_budget"], run["stall_checks"],
                   run["max_planner_calls_per_sim"] * run["sim_budget"])


def planner_steps(run: RunRecord) -> list[Step]:
    return [s for s in run.steps if s.agent == "planner"]


def checked_steps(run: RunRecord) -> list[Step]:
    return [s for s in run.steps if s.report is not None]


def best_step(run: RunRecord) -> Step | None:
    return min(checked_steps(run), key=lambda s: s.report.score, default=None)


def find_duplicate(run: RunRecord, candidate: Candidate) -> int | None:
    """Step.n of an earlier checked step with the same chain (defaults filled in)."""
    fp = fingerprint(candidate)
    return next((s.n for s in checked_steps(run) if fingerprint(s.candidate) == fp), None)


def all_pass(step: Step) -> bool:
    r = step.report
    return r.dc_ok and not r.errors and bool(r.results) and all(m.status == "pass" for m in r.results)


def route(run: RunRecord, cfg: RouterConfig) -> str | None:
    """Return a stop_reason, or None to continue with the Planner."""
    planned = planner_steps(run)
    checked = checked_steps(run)
    if planned and planned[-1].report is not None and all_pass(planned[-1]):
        return "all_pass"
    if run.sims_used >= cfg.sim_budget or len(planned) >= cfg.max_planner_calls:
        return "budget"
    scores = [s.report.score for s in checked]
    n = cfg.stall_checks
    if len(scores) > n and min(scores[-n:]) >= min(scores[:-n]):
        return "stall"
    if len(planned) >= 2 and all(s.duplicate_of is not None for s in planned[-2:]):
        return "duplicate"
    return None
