# OPTIFLOW-X application image: FastAPI + the built dashboard + the agents.
# Untrusted candidate code never runs in this container: it drives the
# host's Docker daemon (socket mount) to start locked-down sandbox
# containers from the `optiflow-sandbox` image. See deploy/README.md.

# --- 1. dashboard (static export) ---------------------------------------------
FROM node:20.18-slim AS dashboard
WORKDIR /dashboard
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY dashboard/ ./
RUN npm run build

# --- 2. runtime -------------------------------------------------------------------
FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_DISABLE_PROGRESS_BARS=1 \
    CREWAI_DISABLE_TELEMETRY=true
WORKDIR /app

# constraints.txt pins every package to the versions the test suite passed
# with (pip freeze of the development environment), so the deployed image
# runs exactly what was tested. CPU-only torch first, so sentence-transformers
# doesn't pull CUDA wheels (GBs).
COPY requirements.txt constraints.txt ./
RUN pip install --index-url https://download.pytorch.org/whl/cpu "torch==$(grep -i '^torch==' constraints.txt | cut -d= -f3)"
RUN pip install -r requirements.txt -c constraints.txt

COPY optiflow/ optiflow/
COPY benchmarks/ benchmarks/
COPY results/ results/
COPY pyproject.toml README.md STATUS.md ./
COPY --from=dashboard /dashboard/out dashboard/out

# Pre-build the knowledge base and cache the embedding model in the image,
# so the first request doesn't download anything.
RUN python -m optiflow.knowledge.ingest

RUN useradd --create-home --uid 10001 optiflow && chown -R optiflow /app
# The docker socket's group differs per host; compose adds it via group_add.
USER optiflow

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
CMD ["python", "-m", "optiflow", "serve", "--host", "0.0.0.0", "--port", "8000"]
