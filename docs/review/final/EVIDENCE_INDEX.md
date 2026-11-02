# OPTIFLOW-X: Artifact & Evidence Index

**Audience:** Faculty & Review Panel  
**Purpose:** Comprehensive directory of all implementation artifacts, test logs, empirical data files, traces, and demo capture targets supporting the course rubric requirements.

---

## 1. Core Source & Implementation Artifacts

| Category | File Path | Description |
|---|---|---|
| **Pydantic Schemas** | [`optiflow/core/schemas.py`](file:///e:/agentic/OPTIFLOW-X/optiflow/core/schemas.py) | Full type contracts for `OptimizationPlan`, `Candidate`, `BuildResult`, `CompareResult`, `RunState`, and `Verdict`. |
| **Messaging Channels** | [`optiflow/comms/blackboard.py`](file:///e:/agentic/OPTIFLOW-X/optiflow/comms/blackboard.py)<br>[`optiflow/comms/p2p.py`](file:///e:/agentic/OPTIFLOW-X/optiflow/comms/p2p.py)<br>[`optiflow/comms/broadcast.py`](file:///e:/agentic/OPTIFLOW-X/optiflow/comms/broadcast.py) | Implementation of Blackboard, P2P, and Broadcast state channels with standard routing. |
| **FastMCP Server** | [`optiflow/mcp_server/server.py`](file:///e:/agentic/OPTIFLOW-X/optiflow/mcp_server/server.py)<br>[`optiflow/agents/mcp_tools.py`](file:///e:/agentic/OPTIFLOW-X/optiflow/agents/mcp_tools.py) | Standalone FastMCP server running over stdio; exposes 7 sandboxed compilation and benchmarking tools. |
| **A2A Interop** | [`optiflow/interop/adk_reviewer.py`](file:///e:/agentic/OPTIFLOW-X/optiflow/interop/adk_reviewer.py)<br>[`optiflow/interop/a2a_server.py`](file:///e:/agentic/OPTIFLOW-X/optiflow/interop/a2a_server.py)<br>[`optiflow/interop/a2a_client.py`](file:///e:/agentic/OPTIFLOW-X/optiflow/interop/a2a_client.py) | Google ADK `LlmAgent` served with `to_a2a` and consumed by CrewAI pipeline via official `a2a-sdk`. |
| **Guardrails & Safety** | [`optiflow/security/guardrails.py`](file:///e:/agentic/OPTIFLOW-X/optiflow/security/guardrails.py)<br>[`optiflow/agents/safety.py`](file:///e:/agentic/OPTIFLOW-X/optiflow/agents/safety.py) | Multi-layer input injection filter, comment sanitizer, and C AST syscall safety filter. |
| **Observability** | [`optiflow/observability/tracing.py`](file:///e:/agentic/OPTIFLOW-X/optiflow/observability/tracing.py)<br>[`optiflow/observability/metrics.py`](file:///e:/agentic/OPTIFLOW-X/optiflow/observability/metrics.py)<br>[`optiflow/observability/judge.py`](file:///e:/agentic/OPTIFLOW-X/optiflow/observability/judge.py) | OpenTelemetry span tracer, per-agent latency/cost/token metrics, and LLM rubric judge. |
| **Deployment** | [`Dockerfile`](file:///e:/agentic/OPTIFLOW-X/Dockerfile)<br>[`docker/sandbox.Dockerfile`](file:///e:/agentic/OPTIFLOW-X/docker/sandbox.Dockerfile)<br>[`docker-compose.yml`](file:///e:/agentic/OPTIFLOW-X/docker-compose.yml)<br>[`deploy/vm-startup.sh`](file:///e:/agentic/OPTIFLOW-X/deploy/vm-startup.sh) | Production multi-stage Docker build, hardened sandbox container, compose stack, and Google Compute Engine startup script. |

---

## 2. Empirical Datasets & Statistical Reports

| Artifact Path | Format | Description / Content |
|---|:---:|---|
| [`results/runs.csv`](file:///e:/agentic/OPTIFLOW-X/results/runs.csv) | CSV | **Master dataset containing 196 runs** recording run ID, experiment, program, architecture, messaging, speedup, stop reason, latency, tokens, and cost. |
| [`results/analysis.json`](file:///e:/agentic/OPTIFLOW-X/results/analysis.json) | JSON | Aggregated statistical report: geometric mean speedups, Wilson 95% confidence intervals, Holm-Wilcoxon paired tests, and Pareto frontiers. |
| [`results/experience.jsonl`](file:///e:/agentic/OPTIFLOW-X/results/experience.jsonl) | JSONL | Cross-run memory containing judged LLM attempts used to train the XGBoost offline prior model. |
| [`results/figures/pareto.png`](file:///e:/agentic/OPTIFLOW-X/results/figures/pareto.png) | PNG Image | Generated Pareto frontier plot: Mean Cost (USD) vs. Optimization Success Rate. |
| [`results/figures/speedup_per_program.png`](file:///e:/agentic/OPTIFLOW-X/results/figures/speedup_per_program.png) | PNG Image | Empirical speedup distribution across the benchmark programs. |
| `results/runs/<run_id>/report.json` | JSON | Complete `RunState` snapshot for each run, including configuration, attempt history, and verdict. |
| `results/runs/<run_id>/diff.patch` | Patch | Unified diff between original baseline code and accepted optimized rewrite. |
| `results/runs/<run_id>/best.c` | C/C++ | Complete source code of the best accepted optimization. |
| `results/runs/<run_id>/events.jsonl` | JSONL | Raw callback event log capturing step transitions, thoughts, and tool invocations. |

---

## 3. Tracing & Verification Logs

| Artifact Path | Format | Verification Purpose |
|---|:---:|---|
| `results/traces/<run_id>.jsonl` | JSONL | OpenTelemetry span logs recording duration, model name, input/output tokens, and dollar cost per agent. |
| `results/traces/adk_reviewer.jsonl` | JSONL | Dedicated audit trail for Google ADK Verification Reviewer callback events. |

---

## 4. Live Screenshots to Capture During Demo

To preserve document integrity and avoid fabricating unverified screenshots, capture these visual artifacts directly from the live demonstration and save them to `docs/review/final/screenshots/`:

| Screenshot ID | Capture Target | Recommended Save Path | Significance |
|---|---|---|---|
| `SS-01` | **Dashboard: E2 Messaging Comparison**<br>`http://localhost:8000/experiments` | `docs/review/final/screenshots/01_e2_messaging.png` | Shows the 12-cell empirical table comparing Blackboard, P2P, and Broadcast across speedup and latency. |
| `SS-02` | **Dashboard: E1 Architecture Comparison**<br>`http://localhost:8000/experiments` | `docs/review/final/screenshots/02_e1_architecture.png` | Shows Sequential vs. Hierarchical vs. Event-driven speedup and runtime differences. |
| `SS-03` | **Dashboard: Per-Agent Observability**<br>`http://localhost:8000/agents` | `docs/review/final/screenshots/03_agent_observability.png` | Shows median and P95 latency bars, token volume, and critical path identification across the 7 agents. |
| `SS-04` | **Dashboard: Run Detail & Interactive Timeline**<br>`http://localhost:8000/run/?id=0fd81a5ebb8449ab8af2fc2bd29bca2c` | `docs/review/final/screenshots/04_run_timeline_receipts.png` | Shows live WebSocket event timeline, diff view, and "Receipts" checklist confirming guardrail passes. |
| `SS-05` | **Terminal: ADK ↔ CrewAI A2A Test** | `docs/review/final/screenshots/05_a2a_test_terminal.png` | Captures terminal execution of `.venv\Scripts\pytest tests/test_interop.py -k test_a2a` passing cleanly. |
| `SS-06` | **Terminal: FastMCP Stdio Registration** | `docs/review/final/screenshots/06_mcp_tools_terminal.png` | Captures terminal output showing all 7 MCP tools registered with Pydantic schemas. |

---

## 5. Verification & Integrity Statements

- **Cloud Deployment Notice:** The container images (`Dockerfile`, `docker/sandbox.Dockerfile`) and orchestration stack (`docker-compose.yml`) have been verified locally. No public cloud VM is currently provisioned or claimed as live.
- **Data Authenticity:** All 196 rows in `results/runs.csv` and associated JSON reports are authentic empirical records generated during active runs on this machine; zero synthetic rows were injected.
