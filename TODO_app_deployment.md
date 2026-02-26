# App deployment on Scaleway

## Options

### Easiest: Serverless Containers
Package the app as a Docker image, push to Scaleway Container Registry, and deploy
via Serverless Containers. Scales to zero when idle (cheap for a demo/research app).

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install uv && uv sync --no-dev
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "webapp.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Most control: Instances (VPS)
A DEV1-S (~€3.99/mo) is plenty for this workload. SSH in, clone the repo, run
uvicorn behind nginx as a reverse proxy.

## Things to sort out before deploying

- The app reads data files from local paths (`data/processed/` parquet files).
  Options:
  - Bundle the files into the Docker image, or
  - Fetch them from **Scaleway Object Storage** on startup.
- If the Snakemake pipeline also needs to run on the server, a plain Instance is
  easier than containers.

## Recommendation

- **Webapp only** (data pre-generated locally): use Serverless Containers — zero
  maintenance, data served from Object Storage.
- **Pipeline + webapp on same machine**: use a small Instance.
