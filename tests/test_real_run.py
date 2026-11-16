"""One real run with Claude (costs money, roughly $1-2). Skipped unless ANTHROPIC_API_KEY is set
in the environment or in .env. Run alone with:  python -m pytest -s tests/test_real_run.py"""
import io
import os

import pytest
from dotenv import load_dotenv

from pedal_agent.cli import main
from pedal_agent.graph import RunStore
from pedal_agent.schemas import RunRecord

load_dotenv()
pytestmark = pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set")


def test_real_run_warm_overdrive(tmp_path):
    out = io.StringIO()
    main(["run", "--goal", "warm mid-forward overdrive with light breakup", "--auto-approve", "--no-feedback",
          "--llm", "real", "--runs-dir", str(tmp_path)], out=out)
    print(out.getvalue())  # result table, tokens and cost (visible with -s)
    files = sorted(RunStore(tmp_path).dir.glob("*.json"))
    run = RunRecord.model_validate_json(files[0].read_text(encoding="utf-8"))
    assert run.model_id == "claude-opus-5-5" and run.effort == "medium"
    assert run.status in ("awaiting_feedback", "stopped")
    assert run.spec.targets and run.input_tokens > 0 and run.cost_usd > 0
    assert run.stop_reason in ("all_pass", "budget", "stall", "duplicate", "error")
