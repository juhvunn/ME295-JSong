"""Schema additions for Phase 2: LLM output models and token/cost accounting."""
from pathlib import Path

import pytest

from pedal_agent.config import REPO_ROOT
from pedal_agent.schemas import (LLMUsage, PlannerDecision, RunRecord, Step, ToneDraft)


def free_form_dicts(schema, path="$"):
    """Paths where a JSON schema allows arbitrary keys (unsupported by structured outputs)."""
    found = []
    if isinstance(schema, dict):
        extra = schema.get("additionalProperties")
        if extra not in (None, False):
            found.append(path)
        if schema.get("type") == "object" and "properties" not in schema and "$ref" not in schema:
            found.append(path)
        for key, value in schema.items():
            found += free_form_dicts(value, f"{path}.{key}")
    elif isinstance(schema, list):
        for i, value in enumerate(schema):
            found += free_form_dicts(value, f"{path}[{i}]")
    return found


@pytest.mark.parametrize("model", [PlannerDecision, ToneDraft])
def test_llm_output_models_have_no_free_form_dicts(model):
    assert free_form_dicts(model.model_json_schema()) == []


def test_planner_decision_converts_to_candidate():
    decision = PlannerDecision.model_validate({
        "action": "add_block", "rationale": "more grit",
        "chain": [{"block_id": "fuzz_ff_si", "params": [{"name": "Q_model", "value": "QBC549C"}]},
                  {"block_id": "od_ts808", "params": [{"name": "drive", "value": 0.7}]}],
    })
    cand = decision.to_candidate()
    assert [b.block_id for b in cand.chain] == ["fuzz_ff_si", "od_ts808"]
    assert cand.chain[0].params == {"Q_model": "QBC549C"}
    assert cand.chain[1].params == {"drive": 0.7}
    assert cand.rationale == "more grit"


def test_run_record_cost():
    usage = dict(model_id="m", effort="medium")
    run = RunRecord(run_id="r", project_id="p", model_id="m", effort="medium", status="running",
                    price_in_per_mtok=4.0, price_out_per_mtok=20.0, steps=[
                        Step(n=1, agent="tone_analyst", action="tone_analyst", title="t", why="",
                             llm=LLMUsage(node="tone_analyst", input_tokens=1000, output_tokens=500, **usage)),
                        Step(n=2, agent="human", action="human_approve_spec", title="t", why=""),
                        Step(n=3, agent="planner", action="initial_chain", title="t", why="",
                             llm=LLMUsage(node="planner", input_tokens=3000, output_tokens=1500, attempts=2, **usage)),
                    ])
    assert (run.input_tokens, run.output_tokens) == (4000, 2000)
    assert run.cost_usd == pytest.approx((4000 * 4.0 + 2000 * 20.0) / 1e6)  # $0.056


def test_example_run_still_validates_with_new_fields():
    path = REPO_ROOT / "runs" / "example-jazz-christmas.json"
    run = RunRecord.model_validate_json(path.read_text(encoding="utf-8"))
    assert run.cost_usd == 0.0 and all(s.validation_errors == [] for s in run.steps)
