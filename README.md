# ME295 project

Multi-agent guitar amp (preamp/overdrive) circuit design with ngspice feedback.
See `CLAUDE.md` for the project brief and `LOG.md` for the AI use log.

## Setup

```
conda activate <env>
pip install -r requirements.txt
```

ngspice 41 must be installed; set `ngspice.executable` in `config.yaml` to its path
if it is not on PATH (on Windows use the console build, `ngspice_con.exe`).

## Run

```
python scripts/run_diode_clipper.py   # AC + transient sim of the diode clipper
pytest                                # Checker validation tests
```
