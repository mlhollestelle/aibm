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

## Notebooks

To work with the Jupyter notebooks, install the notebooks extra:

```sh
uv sync --extra notebooks
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
