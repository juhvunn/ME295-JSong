# AI Use Log

Record of Claude Code contributions for the AI Use Declaration.

| Date | What | Files |
|------|------|-------|
| 2026-11-01 | Created a scratch project folder; wrote CLAUDE.md from the user-provided project brief (verbatim) and started this log | CLAUDE.md, LOG.md |
| 2026-11-01 | Moved CLAUDE.md and LOG.md into ME295-JSong and removed the empty scratch folder; added .gitignore; filled the Repo placeholder in CLAUDE.md (ENV_NAME/VERSION left as TODO: no conda/Python found on machine) | CLAUDE.md, LOG.md, .gitignore |
| 2026-11-01 | Scaffolded target layout: config.yaml (model ID placeholder), requirements.txt, pytest.ini, block library / protocol / targets YAML skeletons, src package stubs (config loader, validate, evaluate, memory), README setup notes, logs/.gitkeep | config.yaml, requirements.txt, pytest.ini, README.md, blocks/block_library.yaml, protocol/protocol_v1.yaml, targets/targets_v1.yaml, src/__init__.py, src/config.py, src/memory.py, src/tools/__init__.py, src/tools/validate.py, src/tools/evaluate.py, src/agents/__init__.py, src/baselines/__init__.py, logs/.gitkeep |
| 2026-11-01 | Implemented src/tools/simulate.py: netlist safety check (forbidden dot-directives; allowlist of .control commands; wrdata bare filenames only), save netlist to runs/<id>/, run `ngspice -b` with timeout (log to logs/<id>.log), wrdata text parser using numpy | src/tools/simulate.py |
| 2026-11-01 | Added trusted netlist templates (diode clipper with AC + transient, RC low-pass), src/tools/build.py (fills templates with validated numeric values only), scripts/run_diode_clipper.py (runs sims, parses wrdata text output with numpy, prints summary) | src/tools/templates/diode_clipper.cir, src/tools/templates/rc_lowpass.cir, src/tools/build.py, scripts/run_diode_clipper.py |
| 2026-11-01 | Added f_minus3db Checker metric to src/tools/evaluate.py and tests/test_rc_lowpass.py (analytic -3 dB check, ngspice RC low-pass vs 1/(2*pi*R*C) within 1%, netlist filter tests). NOT YET RUN: no Python/ngspice on this machine | src/tools/evaluate.py, tests/test_rc_lowpass.py |
| 2026-11-01 | Updated the documented environment to conda ME295 / Python 3.12.15 and ignored ngspice log files; the user verified the RC -3 dB test in their own pytest run (8 passed, 0 skipped) | CLAUDE.md, .gitignore, LOG.md |
| 2026-11-01 | Wrote a headless plotting CLI for AC response, transient, transfer curve, and visual-only spectrum; added synthetic plotting coverage, matplotlib dependency, and generated PNG ignore rule | scripts/plot_results.py, tests/test_plot_results.py, requirements.txt, .gitignore, LOG.md |
