# aibm

## Prerequisites

This project uses LLMs to power agent decisions. It supports three providers:

- [Gemini API](https://aistudio.google.com/) (default)
- [Anthropic API](https://platform.claude.com/)
- [OpenAI API](https://platform.openai.com/)

Set the API key for the provider you want to use:

```sh
# For Gemini (default)
export GEMINI_API_KEY=your_key_here

# For Anthropic
export ANTHROPIC_API_KEY=your_key_here

# For OpenAI
export OPENAI_API_KEY=your_key_here
```

To make this permanent, add the line to your shell config (e.g. `~/.bashrc` or `~/.zshrc`).

The provider is selected automatically based on the model name. Names starting
with `claude` use Anthropic; names starting with `gpt-`, `o1`, or `o3` use
OpenAI; everything else uses Gemini:

```python
from aibm import Agent

# Uses Gemini (default)
agent = Agent(name="Alice")

# Uses Anthropic
agent = Agent(name="Alice", model="claude-sonnet-4-20250514")

# Uses OpenAI
agent = Agent(name="Alice", model="gpt-4o")
```

## Get started

Install the package in editable mode with dev tools:

```sh
uv sync
```

Run tests:

```sh
uv run pytest
```

Run a script:

```sh
uv run python scripts/example.py
```

## Notebooks

To work with the Jupyter notebooks, install the notebooks group:

```sh
uv sync --group notebooks
```

Launch JupyterLab:

```sh
uv run jupyter lab
```

The `notebooks/` directory contains hands-on explorations of the model components:

- **synthetic_population.ipynb** — manually build a small population of zones, households, and agents

## Lint and format

```sh
uv run ruff check src tests
uv run ruff format src tests
```

Activate pre-commit hooks (runs ruff automatically on every `git commit`):

```sh
uv run pre-commit install
```

## Example model

The package is used to develop an example model for the Walcheren
region in the Netherlands. Walcheren consists of municipalities
Middelburg, Veere and Vlissingen.

### Input data

* Demographic data for population synthesis from
  [CBS Vierkantstatistieken](https://download.cbs.nl/vierkant/100/2025-cbs_vk100_2024_v1.zip).
  Place the zip in `data/raw/`.

### Running the pipeline

Install the pipeline dependencies and run Snakemake:

```sh
uv sync --group pipeline
uv run snakemake --cores 1 -s workflow/Snakefile
```

The pipeline steps are:

1. **download_boundaries** — fetch Walcheren municipality
   polygons from PDOK
2. **filter_grid** — spatial-filter CBS 100m grid to Walcheren
3. **clean** — handle anonymisation, remap age groups, derive
   household size distributions
4. **build_specs** — convert cleaned data to ZoneSpec objects
5. **synthesize** — generate synthetic population

Output lands in `data/processed/walcheren_population.parquet`.

## Web app

Visualise simulation results on an interactive map.

```sh
uv sync --group webapp

# Prepare data (after running the pipeline)
uv run python webapp/prepare_data.py --config workflow/config.yaml

# Start the server
uv run uvicorn webapp.app:app --reload
```

Open http://127.0.0.1:8000 in your browser.
