# aibm

## Prerequisites

This project uses the [Gemini API](https://aistudio.google.com/) to power agent decisions. You need an API key set in your environment before running the model.

```sh
export GEMINI_API_KEY=your_key_here
```

To make this permanent, add the line to your shell config (e.g. `~/.bashrc` or `~/.zshrc`).

## Get started

Install the package in editable mode with dev tools:

```sh
uv sync --extra dev
```

Run tests:

```sh
uv run pytest
```

Run a script:

```sh
uv run python scripts/example.py
```

Lint and format:

```sh
uv run ruff check src tests
uv run ruff format src tests
```

Activate pre-commit hooks (runs ruff automatically on every `git commit`):

```sh
uv run pre-commit install
```

## Synthetic population

The `synth_pop` package generates a synthetic population (buildings → households → persons) from OpenStreetMap data. Install its dependencies with:

```sh
uv sync --extra dev --extra synth_pop
```

Run the pipeline for Veere:

```sh
uv run python scripts/generate_synth_pop.py
```

Outputs are written to `data/` (gitignored):

| File | Contents |
|---|---|
| `data/households.csv` | household_id, building_osmid, centroid_x, centroid_y |
| `data/persons.csv` | person_id, household_id, age |
| `data/buildings.gpkg` | Building polygons, EPSG:28992 |
