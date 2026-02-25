"""FastAPI server for the AIBM web app.

Serves static files and the single-page visualisation app.

Usage:
    uv run uvicorn webapp.app:app --reload
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="AIBM Visualisation")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
