"""Command line: python -m pedal_agent run --goal "..." [options]."""
import argparse
import sys

from pedal_agent.graph import Agent, RunStore, new_run
from pedal_agent.llm import FakeLLM
from pedal_agent.prompts import report_table
from pedal_agent.schemas import MetricTarget, RunRecord


def make_llm(kind: str):
    if kind == "fake":
        return FakeLLM()
    from pedal_agent.llm import AnthropicLLM  # step 8
    return AnthropicLLM()


def _b(v) -> str:
    return "" if v is None else f"{v:g}"


def print_targets(targets: list[MetricTarget], out) -> None:
    print(f"  {'#':>2}  {'metric':12s} {'lo':>8s} {'hi':>8s}  {'unit':5s} label", file=out)
    for i, t in enumerate(targets, 1):
        print(f"  {i:>2}  {t.name:12s} {_b(t.lo):>8s} {_b(t.hi):>8s}  {t.unit:5s} {t.label}", file=out)


def ask_spec(spec: dict, ask, out) -> dict:
    targets = [MetricTarget.model_validate(t) for t in spec["targets"]]
    print("\nProposed targets:", file=out)
    print_targets(targets, out)
    while True:
        choice = ask("[a]pprove / [e]dit / [r]eject: ").strip().lower()
        if choice in ("a", "approve"):
            return {"action": "approve"}
        if choice in ("r", "reject"):
            return {"action": "reject", "why": ask("Reason (optional): ").strip()}
        if choice in ("e", "edit"):
            edited = []
            for t in targets:
                lo = ask(f"  {t.label} lo [{_b(t.lo) or 'none'}] (Enter keeps, - for none): ").strip()
                hi = ask(f"  {t.label} hi [{_b(t.hi) or 'none'}] (Enter keeps, - for none): ").strip()
                upd = {}
                for key, val in (("lo", lo), ("hi", hi)):
                    if val == "-":
                        upd[key] = None
                    elif val:
                        upd[key] = float(val)
                edited.append(t.model_copy(update=upd))
            print("\nEdited targets:", file=out)
            print_targets(edited, out)
            return {"action": "approve", "targets": [t.model_dump(mode="json") for t in edited]}


def print_summary(run: RunRecord, path, out) -> None:
    print(f"\nRun {run.run_id}: status={run.status}, stop_reason={run.stop_reason}", file=out)
    for s in run.steps:
        print(f"  {s.n:>2}. [{s.agent}] {s.action}: {s.title}", file=out)
        for e in s.validation_errors:
            print(f"        rejected: {e}", file=out)
    best = run.best
    if best:
        print(f"\nBest: step {best.n}, chain {' → '.join(b.block_id for b in best.candidate.chain)}, "
              f"score {best.report.score:.3g}", file=out)
        for b in best.candidate.chain:
            print(f"  {b.block_id}: {b.params or 'defaults'}", file=out)
        print(f"  {'metric':12s} {'target':>16s} {'measured':>10s}  status", file=out)
        for row in report_table(run.spec, best.report):
            print(f"  {row['metric']:12s} {row['target']:>16s} {row['measured']:>10g}  {row['status']}", file=out)
    print(f"\nSimulations {run.sims_used}/{run.sim_budget}, topology changes {run.topology_changes}, "
          f"tokens in/out {run.input_tokens}/{run.output_tokens}, cost ${run.cost_usd:.4f} "
          f"({run.model_id}, effort {run.effort})", file=out)
    if run.placeholder_or_unvalidated:
        print("WARNING: placeholder/unregistered model files or unvalidated choices were used "
              "(see model_files in the run file): not for reported results.", file=out)
    print(f"Run file: {path}", file=out)


def cmd_run(args, ask, out) -> int:
    llm = make_llm(args.llm)
    agent = Agent(llm, RunStore(args.runs_dir))
    try:
        run = new_run(args.goal, llm, genre=args.genre, mode=args.mode)
        print(f"Run {run.run_id} ({args.mode}, llm={args.llm})", file=out)
        pending = agent.start(run)
        while pending:
            if pending["kind"] == "approve_spec":
                answer = {"action": "approve"} if args.auto_approve else ask_spec(pending["spec"], ask, out)
            else:  # feedback
                if args.no_feedback:
                    break
                print_summary(agent.store.load(run.run_id), agent.store.path(run.run_id), out)
                text = ask("\nFeedback for the Planner, 'accept', or Enter to leave the run paused: ").strip()
                if not text:
                    break
                answer = {"action": "accept"} if text.lower() == "accept" else {"action": "feedback", "text": text}
            pending = agent.resume(run.run_id, answer)
        final = agent.store.load(run.run_id)
        print_summary(final, agent.store.path(run.run_id), out)
        return 0 if final.status != "stopped" else 1
    finally:
        agent.close()


def main(argv=None, ask=input, out=None) -> int:
    out = out or sys.stdout
    if hasattr(out, "reconfigure"):
        out.reconfigure(errors="replace")  # e.g. '→' on a cp1252 console
    p = argparse.ArgumentParser(prog="python -m pedal_agent")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the design agent for a tone goal")
    r.add_argument("--goal", required=True)
    r.add_argument("--genre")
    r.add_argument("--auto-approve", action="store_true", help="approve the target spec without asking")
    r.add_argument("--no-feedback", action="store_true", help="leave the run paused at the end instead of asking")
    r.add_argument("--mode", choices=["agent", "baseline_fixed_topology"], default="agent")
    r.add_argument("--llm", choices=["real", "fake"], default="real")
    r.add_argument("--runs-dir", help=argparse.SUPPRESS)  # tests
    args = p.parse_args(argv)
    return cmd_run(args, ask, out)
