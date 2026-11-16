# ME295 project

Multi-agent guitar amp (preamp/overdrive) circuit design with ngspice feedback.
See `CLAUDE.md` for the project brief, `docs/DASHBOARD_SPEC.md` for the plan,
and `LOG.md` for the AI use log.

## Setup

```
conda activate <env>
pip install -r requirements.txt
```

ngspice 41 must be installed; set `ngspice.executable` in `config.yaml` to its path
if it is not on PATH (on Windows use the console build, `ngspice_con.exe`).

## Run

From the repo root:

```
python -m pedal_agent run --goal "warm mid-forward overdrive" --llm fake   # agent, no API cost
python -m pedal_agent run --goal "..."      # real Claude (ANTHROPIC_API_KEY in .env)
pytest                                # quick suite (~25 s): skips tests marked slow
pytest --full                         # full suite (~75 s): also the slow 12-simulation runs; run before commits
python -m tests.smoke_block           # DC/AC/THD smoke test of every pedal block
python -m examples.make_example_run   # rebuild runs/example-jazz-christmas.json
python scripts/run_diode_clipper.py   # AC + transient sim of the reference diode clipper
```
