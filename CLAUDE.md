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

* When adding a function, always add at least one test too.
* Keep lines to a maximum of 88 characters.

## Git

* Never commit to main/master branch. Create feature branch first if on main/master.

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
