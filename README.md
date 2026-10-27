# OPTIFLOW-X

Measurement-driven multi-agent optimization of C/C++ programs.

OPTIFLOW-X takes a slow C program, profiles it, has a team of LLM agents
propose source- and flag-level optimizations, and accepts a change only
when real tools agree:

- it **compiles** (whitelisted flags, in a locked-down Docker sandbox),
- its output **matches the reference** on three inputs (including n=1 and
  odd sizes like 33) *and* it exits cleanly,
- an **AddressSanitizer + UBSan** build of it runs clean on the small inputs,
- it is **faster under a significance test**: baseline and candidate are timed
  interleaved in the same container, and the median speedup must be
  >= 1.05x with a one-sided Mann-Whitney U p < 0.05,
- and it beats the best candidate found so far.

The accept/reject decision and the stopping rule are deterministic code.
LLMs propose; tools dispose.

The project is also a small research study: the same loop runs under three
architectures (sequential, hierarchical, event-driven), three messaging
mechanisms (blackboard, peer-to-peer, broadcast), three prompting styles
(structured, ReAct, reflection), three model assignments, and a set of
ablations, compared on success, speedup, latency and cost.

## Course requirements

[`REQUIREMENTS.md`](REQUIREMENTS.md) maps each course requirement (shared
state and messaging, MCP tools, Pydantic output, agentic patterns,
callbacks, A2A across CrewAI and Google ADK, guardrails, observability,
evaluation, deployment) to the code, the tests and the evidence.

## Status

See [`STATUS.md`](STATUS.md) for what has been measured so far, what hasn't,
and known limitations. The short version: the system is complete end to end
(all three architectures, all three messaging modes, all three prompting
styles, ablations, tracing, statistics, dashboard), every component is
tested, and the experiment matrix is ready to run. How many experiment cells
have actually been run is recorded in `results/runs.csv`.

## Quick start

Requirements: Python 3.11, Docker, Node 20+ (only to rebuild the dashboard).

```bash
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

docker build -t optiflow-sandbox -f docker/sandbox.Dockerfile .
copy .env.example .env          # add an API key (one Gemini key is enough)
python -m optiflow.knowledge.ingest

cd dashboard && npm install && npm run build && cd ..
uvicorn optiflow.api.main:app --port 8000
```

Open http://localhost:8000. Without an API key, the flags-only and rule-based
baselines still run.

From the command line:

```bash
python -m optiflow doctor                         # check Docker, image, keys, knowledge base
python -m optiflow run matmul_naive               # one run, live step-by-step output
python -m optiflow run lcs --arch event --messaging p2p --prompt reflection
python -m optiflow run bubble_sort --variant flags_only
python -m optiflow serve                          # same as the uvicorn command above
``` For dashboard development, `npm run dev` in `dashboard/`
serves on :3000 and talks to the API on :8000.

## How one run works

| # | Agent | What it does | Tools |
|---|---|---|---|
| 1 | Analyzer | tree-sitter: loops, nesting, features; LLM writes a short structural summary | MCP `get_program`, `static_analysis` |
| 2 | Profiler | `perf stat` counters (IPC, L1/LLC, branches) and `perf record` samples rolled up onto loops; cachegrind/gprof fallback | MCP `profile_program` |
| 3 | Strategist | plans 1-2 strategies from the source, profile, RAG technique cards and the strategy predictor | local RAG + predictor (tools in ReAct mode) |
| 4 | Transformer | rewrites the current best source; output passes a safety filter | none |
| 5 | Compiler & Executor | compiles; LLM self-repairs compile errors (max 2); runs tests and sanitizers | MCP `compile_code`, `run_tests` |
| 6 | Benchmark | interleaved baseline-vs-candidate timing, 10-30 runs | MCP `compare_to_baseline` |
| 7 | Critic | rules decide; on rejection the LLM writes feedback for the Strategist | none |

Accepted changes stack: the next attempt starts from the best candidate.
The run stops on the attempt budget, the USD cap, two accepted attempts in a
row that each gain < 3%, or three rejections in a row.

Every tool call goes through one MCP stdio session to
`optiflow/mcp_server/server.py`; no agent touches Docker directly. Every
step is an OpenTelemetry span with model, tokens and cost
(`results/traces/<run_id>.jsonl`), and every run is saved to
`results/runs/<run_id>/` plus a row in `results/runs.csv`.

### Two frameworks, one protocol

The seven-agent team is built with **CrewAI**. Rejection feedback can
instead come from a **Google ADK** agent (the Verification Reviewer),
served with ADK's `to_a2a` and called by the CrewAI pipeline over the
**A2A protocol** (`critic_backend: adk_a2a`, or `--critic adk_a2a` on the
CLI). In docker-compose the reviewer is a separate service.

### Guardrails

User guidance, program source (C comments are an injection vector) and
LLM output are screened for prompt injection and abusive language; CrewAI
task guardrails force well-formed, safe plans and rewrites; every MCP
tool result is type-checked. See the dashboard's Security page.

### Architectures, messaging, prompting

- **Sequential**: fixed loop in Python.
- **Hierarchical**: a Manager LLM chooses `plan` / `retransform` / `stop` each turn, inside deterministic guardrails.
- **Event-driven**: handlers on an event bus; profiling the baseline runs in parallel with the Analyzer.
- **Messaging**: all step inputs are read *from the channel*. Blackboard lets agents pull any topic; peer-to-peer delivers only along a routing table; broadcast pushes everything into every inbox. What the Strategist sees, and pays tokens for, differs accordingly.
- **Prompting**: structured (RAG + ranking injected), ReAct (RAG + ranking as tools the agent calls), reflection (draft, self-critique, revise), few-shot (worked examples); plus four Strategist personas (content variance).

## Measurement

- `hrtime` (`docker/hrtime.c`): CLOCK_MONOTONIC wall time, CPU time and peak RSS via `wait4`.
- Binaries and input are staged in the container's tmpfs before timing; reading input from the Docker Desktop bind mount made wall time erratic.
- Inputs are sized so most baselines run 0.3-2 s at -O2.
- `python -m optiflow.experiments.stability` measures CV per program across sessions and writes `results/stability.json` and `results/machine.json`; short programs get more repetitions automatically.

## Strategy predictor

`python -m optiflow.ml.run_sweep` benchmarks, without any LLM, four flag
variants for all 50 programs plus 27 hand-written single-strategy rewrites,
each verified against the reference outputs. Untested strategies stay
unlabeled (not negative). `python -m optiflow.ml.train_xgb` trains one small
classifier per strategy, evaluates it leave-one-program-out, and uses it
only where it beats the static heuristic on held-out programs. The
dashboard's Predictor page shows which strategies earned a model.

## Experiments

```bash
python -m optiflow.experiments.run_matrix optiflow/experiments/configs/e0_baselines.yaml
python -m optiflow.experiments.run_matrix optiflow/experiments/configs/e1_architecture.yaml --programs matmul_naive lcs
python -m optiflow.experiments.analyze_results          # results/analysis.json + figures
python -m optiflow.observability.judge score            # LLM-judge scores for every plan
```

The runner is resumable (finished cells are skipped). Configs: E0 LLM-free
baselines, E1 architecture, E2 messaging, E3 prompting, E4 model
assignment, E5 ablations. Analysis reports geometric-mean speedup, success
with Wilson intervals, Friedman + Holm-corrected Wilcoxon tests on paired
programs, cost/latency percentiles and a cost-vs-success Pareto front.

## Deployment

`docker compose build sandbox && docker compose up -d --build` runs the
app and the ADK reviewer. It needs a host with a Docker daemon (a VM, not
serverless); `deploy/README.md` has a Google Compute Engine recipe.

## Tests

```bash
pytest tests/        # Docker must be running
```

`tests/test_architectures.py` runs all three architectures end to end
(real sandbox, compiler, sanitizers, benchmark) with a scripted stand-in for
the LLM, so the orchestration is verified without an API key.

## Repository layout

```
optiflow/
  core/           schemas, config + model routing + pricing, LLM metering, budget
  tools/          sandbox, compile, verify (+sanitizers), bench (hrtime), profile (perf), analyze
  mcp_server/     the MCP tool server
  agents/         the seven agents, prompts, MCP client
  architectures/  pipeline steps + sequential / hierarchical / event-driven
  comms/          blackboard / peer-to-peer / broadcast
  knowledge/      technique cards, ingestion, retrieval
  ml/             features, sweep templates, dataset, training, predictor
  observability/  tracing, metrics, LLM judge
  experiments/    configs, matrix runner, stability test, run store, analysis
  api/            FastAPI backend (serves the dashboard build at /)
dashboard/        Next.js dashboard (static export)
benchmarks/       50 programs, inputs, reference outputs
docker/           sandbox image + hrtime harness
tests/
```

## License

Coursework project; no license granted for reuse.
