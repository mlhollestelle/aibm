"""FastAPI server for the AIBM web app.

Serves static files and the single-page visualisation app.

Usage:
    uv run uvicorn webapp.app:app --reload
"""

from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).parent / "static"
CONTENT_DIR = Path(__file__).parent / "content"

app = FastAPI(title="AIBM Visualisation")


@app.get("/content/about.md")
def get_about() -> FileResponse:
    return FileResponse(CONTENT_DIR / "about.md", media_type="text/plain")


@app.get("/api/config")
def get_config() -> JSONResponse:
    with (CONTENT_DIR / "config.yaml").open() as f:
        data = yaml.safe_load(f)
    return JSONResponse(
        {
            "github_url": data.get("github_url", ""),
            "linkedin_url": data.get("linkedin_url", ""),
        }
    )


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
