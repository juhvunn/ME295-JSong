"""AI-free planners for the Phase 3 baselines. They implement the LLM interface (generate ->
(PlannerDecision, LLMUsage)) so they run through exactly the same graph as the agent: Validate,
Checker, Router, RunRecord. model_id = "none", zero tokens.

  RandomCatalogPlanner      mode random_catalog: random chain (1-2 blocks) and parameters each call
  RandomFixedTopologyPlanner mode random_fixed_topology: random parameters of a fixed chain
                            (od_ts808 in benchmarks; the oracle variant uses the solution's chain)

Each planner remembers the chain it last proposed (starting from the run's start chain), so the
action label matches the chain change and Validate never has to relabel it.
"""
import random

from pedal_agent.baselines.sampling import sample_design
from pedal_agent.llm import LLMOutputError
from pedal_agent.schemas import LLMUsage, PlannerDecision
from pedal_agent.validate import derive_action


class _RandomPlanner:
    model_id = "none"
    effort = "none"

    def __init__(self, seed: int, start_chain: list[str]):
        self.rng = random.Random(seed)
        self.previous = list(start_chain)
        self.calls: list[tuple[str, str]] = []

    def design(self) -> list[tuple[str, dict]]:
        raise NotImplementedError

    def generate(self, node, system, prompt, schema):
        self.calls.append((node, prompt))
        if node != "planner" or schema is not PlannerDecision:
            raise LLMOutputError(f"{type(self).__name__} only plans (asked for {node})")
        design = self.design()
        ids = [b for b, _ in design]
        decision = PlannerDecision.model_validate({
            "action": derive_action(self.previous, ids),
            "rationale": f"random sample ({type(self).__name__})",
            "chain": [{"block_id": b, "params": [{"name": k, "value": v} for k, v in p.items()]} for b, p in design],
        })
        self.previous = ids
        return decision, LLMUsage(node=node, model_id=self.model_id, effort=self.effort,
                                  input_tokens=0, output_tokens=0)


class RandomCatalogPlanner(_RandomPlanner):
    def design(self):
        return sample_design(self.rng)


class RandomFixedTopologyPlanner(_RandomPlanner):
    def __init__(self, seed: int, chain: list[str]):
        super().__init__(seed, chain)
        self.chain = list(chain)

    def design(self):
        return sample_design(self.rng, self.chain)
