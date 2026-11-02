# Deploying OPTIFLOW-X to Render

`deploy/README.md` describes the Docker-socket deployment on a VM. Render
gives a web service no Docker daemon, so this variant carries the C/C++
toolchain in the image and runs candidates with `SANDBOX_BACKEND=local`.

| File | Purpose |
|---|---|
| `Dockerfile.render` | dashboard build + gcc/g++/clang/valgrind/binutils + the Python app |
| `render.yaml` | Blueprint: one Docker web service, a 2 GB disk, health check, env vars |
| `optiflow/tools/sandbox.py` | the `local` sandbox backend |

## Deploy

1. Push this branch to GitHub (`render-deploy`).
2. Render dashboard → **New → Blueprint** → pick the repository and the
   `render-deploy` branch → Apply. Render builds `Dockerfile.render`
   (about 10-15 minutes the first time: CPU torch and the embedding model).
3. Environment tab:
   - `OPTIFLOW_API_TOKEN` is generated for you. Copy it; the workspace asks
     for it once (stored in your browser only) before it starts a run.
   - `GEMINI_API_KEY` (optional) enables the "Smart rewrite" method. Without it
     only the free "Quick tune" method is offered.
4. Open `https://<service>.onrender.com/`.

Instance size: the image loads torch, sentence-transformers, CrewAI and ADK.
`standard` (2 GB) is the render.yaml default; measure before going smaller.
Persistent disks need a paid instance.

## What works differently from the VM deployment

| Area | On Render |
|---|---|
| Sandbox | `local`: an unprivileged uid (10002), scrubbed environment (no API keys), private scratch dir, CPU / memory / process / file-size limits via `prlimit`. **No network or filesystem namespace**, so candidate code could open outbound connections or read world-readable files. This is why starting a run requires the token. |
| Hardware counters | `perf` is unavailable, so the profiler falls back to cachegrind / gprof. Profiles are less detailed than the committed ones. |
| Timing noise | Shared vCPUs, no CPU pinning. The interleaved median + Mann-Whitney test still guards every accept, but expect more "no significant gain" results than on a dedicated machine. Short programs (a few ms) are flagged low-precision. |
| ADK reviewer | started on demand inside the container (no separate A2A service). |
| Persistence | run reports, traces and user programs go to `OPTIFLOW_DATA_DIR` (`/var/data`, the disk). Committed evidence (`results/runs.csv`, stability, figures) is baked into the image and read-only in practice. |
| Historic per-run artifacts | `results/runs/` and `results/traces/` are git-ignored, so the old experiment runs' reports and traces are **not** in the deployed image. |
