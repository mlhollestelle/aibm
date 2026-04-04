# CLAUDE.md

This project is an agent-based travel demand model approach with LLMs plus a web app to show the results.

## General

* This projects is aimed to build a simple-medium advanced ABM that uses LLMs with prompts instead of other statistical models.
* The model results are then to be displayed in a webapp that shows how the agents travel in the model area.
* The model uses Snakemake to run the model pipeline.

## During development

* Do not generate large amounts of code at once, but break steps down in atomic steps
* Make sure best practices are followed/promote best practices.
* `workflow/scripts/simulate.py` and `notebooks/simulation_walkthrough.ipynb` mirror each other. The notebook contains verbatim copies of the helper functions from `simulate.py` (marked with a comment). Any change to those functions in `simulate.py` **must** be reflected in the notebook in the **same commit**.
* Consult the travel-demand-expert.md agent when doing steps which require theoretical input regarding transport modelling.

## Python

* When adding a function to the aibm package, always add at least one test too.
* Keep lines to a maximum of 88 characters.

## Git

* Never commit to main/master branch. Create feature branch first if on main/master.

## Project Structure

```
aibm/
├── src/
│   ├── aibm/                  # Main package: the ABM core
├── workflow/                  # Snakemake pipeline for the Walcheren example model
│   ├── Snakefile              # Pipeline definition and rules
│   ├── config.yaml            # Pipeline configuration (study area, network, simulation)
│   └── scripts/               # One script per pipeline step
├── tests/                     # pytest test suite (mirrors src/aibm/)
├── notebooks/                 # Jupyter notebooks for exploration
├── scripts/                   # Ad-hoc development and experiment scripts
├── data/
│   ├── raw/                   # Raw input data (not in git)
│   └── processed/             # Pipeline outputs (not in git)
├── .claude/
│   └── agents/                # Custom Claude sub-agent definitions
├── pyproject.toml             # Project metadata and dependencies
└── uv.lock                    # Locked dependency versions
```

## Web App

* The web app lives in `webapp/` and visualises simulation results on an interactive map.
* App if ully static and hosted on Cloudflare Pages (`webapp/static/` is the build output directory). No server to maintain.
* Stack:
  * Frontend (vanilla JS, no framework),
  * MapLibre for basemap,
  * deck.gl v9.1.4 — agent/route data layers (ScatterplotLayer, PathLayer)
  * marked.js v12 — renders the about page from Markdown
  * CartoDB Dark Matter — basemap style
  * Inter — UI font (Google Fonts)

### Mode colours

Defined in `webapp/static/js/layers.js` (`MODE_COLORS`). Use these everywhere
(plots, diagrams, docs) so colours are consistent across the webapp and figures:

| Mode    | Hex       | RGB             |
|---------|-----------|-----------------|
| car     | `#2d72d2` | 45, 114, 210    |
| bike    | `#29a634` | 41, 166, 52     |
| transit | `#d1980b` | 209, 152, 11    |
| walk    | `#cd4246` | 205, 66, 70     |

## Workflow / example model

* The `workflow/` directory contains Snakemake pipeline scripts
  for the Walcheren example model. These are **outside** the
  aibm package — they only consume its public API.
* Pipeline dependencies live in the `pipeline` dependency group
  (`uv sync --group pipeline`).
* Raw data goes in `data/raw/`, processed outputs in
  `data/processed/`.
* All pipeline settings (study area name, network modes, simulation
  LLM model, number of households, etc.) live in `workflow/config.yaml`.
  Scripts accept a `--config` flag to override the default path.
* Full pipeline end product is `{name}_assigned_trips.parquet` — trips
  with per-agent routes (node sequences) from all-or-nothing assignment.
* Run the pipeline:
  `uv run snakemake --cores 1 -s workflow/Snakefile`

## Commands

Run tests:
```
uv run pytest
```

Format code:
```
uv run ruff format src tests
```

Lint:
```
uv run ruff check src tests
```

Type check:
```
uv run mypy src/
```
