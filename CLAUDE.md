# CLAUDE.md

This project is a work in progress where someone not experienced with Python builds an agent-based travel demand model approach with LLMs plus aweb app to show the results.

## General

* This projects is aimed to build a simple-medium advanced ABM that uses LLMs with prompts instead of other statistical models.
* The model results are then to be displayed in a webapp that shows how the agents travel in the model area.

## During development

* Guide the developer through python best practices.
* Explain new concepts to the developer through concepts in R — in chat messages only. Never put R references, R analogies, or R terminology in source code, docstrings, comments, or any committed file.
* Do not generate large amounts of it at once, so that the developer can follow and learn
* Make sure best practices are followed.

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
│   │   ├── agent.py           # Agent class (one person in the model)
│   │   ├── household.py       # Household class (group of agents)
│   │   ├── zone.py            # Zone class (geographic unit / TAZ)
│   │   ├── activity.py        # Activity types and data
│   │   ├── trip.py            # Trip between two locations
│   │   ├── tour.py            # Tour (chain of trips from/to home)
│   │   ├── day_plan.py        # Full-day activity schedule for an agent
│   │   ├── synthesis.py       # Population synthesis (create agents from specs)
│   │   ├── llm.py             # LLM client wrappers (Anthropic, Gemini, OpenAI)
│   │   └── __init__.py        # Public API exports
│   └── synth_pop/             # Synthetic population helpers (WIP)
├── workflow/                  # Snakemake pipeline for the Walcheren example model
│   ├── Snakefile              # Pipeline definition and rules
│   ├── config.yaml            # Pipeline configuration (study area, network, simulation)
│   └── scripts/               # One script per pipeline step
│       ├── _config.py              # Shared --config flag loader
│       ├── download_boundaries.py  # Download study area boundary
│       ├── download_network.py     # Download OSM road network
│       ├── clean_grid.py           # Clean CBS grid data
│       ├── filter_grid.py          # Filter grid to study area
│       ├── build_specs.py          # Build zone specs from grid
│       ├── synthesize.py           # Run population synthesis
│       ├── sample_households.py    # Sample households for simulation
│       ├── build_skim.py           # Compute travel time skim matrix
│       ├── export_network.py       # Export network as GeoParquet
│       ├── fetch_pois.py           # Fetch POIs from OSM
│       ├── simulate.py             # Run LLM-based day-plan simulation
│       └── assign_network.py       # All-or-nothing network assignment
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
