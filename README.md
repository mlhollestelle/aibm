# aibm

## Prerequisites

This project uses LLMs to power agent decisions. It supports two providers:

- [Gemini API](https://aistudio.google.com/) (default)
- [Anthropic API](hhttps://platform.claude.com/)

Set the API key for the provider you want to use:

```sh
# For Gemini (default)
export GEMINI_API_KEY=your_key_here

# For Anthropic
export ANTHROPIC_API_KEY=your_key_here
```

To make this permanent, add the line to your shell config (e.g. `~/.bashrc` or `~/.zshrc`).

The provider is selected automatically based on the model name. Names starting with `claude` use Anthropic; everything else uses Gemini:

```python
from aibm import Agent

# Uses Gemini (default)
agent = Agent(name="Alice")

# Uses Anthropic
agent = Agent(name="Alice", model="claude-sonnet-4-20250514")
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
