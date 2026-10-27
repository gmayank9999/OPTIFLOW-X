# Course requirements → where they live

Each requirement, the code that implements it, the tests that prove it,
and the evidence in `results/`. "How to see it" points at the dashboard
(`python -m optiflow serve`, then http://localhost:8000) or a command.

## 1. Context sharing, state, messaging comparison (Blackboard required)

- **State:** every run carries one `RunState` (`optiflow/core/schemas.py`);
  agents exchange only Pydantic models.
- **Messaging:** all step inputs are read *from a channel*
  (`optiflow/architectures/pipeline.py`, `_read`). Three mechanisms in
  `optiflow/comms/`: **Blackboard** (default; shared store, agents pull
  topics), **Peer-to-peer** (routing table), **Broadcast** (every inbox).
  What the Strategist sees differs by mechanism (`_shared_context`).
- **Comparison:** experiment E2 (`configs/e2_messaging.yaml`); per-run
  message / delivery / byte counts in `runs.csv`.
- **Tests:** `tests/test_comms.py`, `tests/test_architectures.py`
  (all three mechanisms end to end).
- **See it:** Run page → "Messaging" table; Experiments → E2.

## 2. Tool integration via MCP (at least two external tools)

- One MCP server, seven tools (`optiflow/mcp_server/server.py`): program
  database, tree-sitter static analysis (file parser), GCC/Clang compiler,
  test runner + sanitizers, `perf` profiler, benchmark harness, baseline
  comparison. Agents reach the sandbox *only* through one MCP stdio session
  (`optiflow/agents/mcp_tools.py`).
- The ADK reviewer additionally uses a FunctionTool over the ChromaDB
  knowledge base.
- **Tests:** `tests/test_mcp_server.py` (incl. real stdio protocol).

## 3. Structured output with Pydantic

- Every agent output is a Pydantic model (`OptimizationPlan`, `Candidate`,
  `BuildResult`, `TestResult`, `CompareResult`, `Verdict`, `RunState`).
- Final output: `results/runs/<id>/report.json` (JSON), `diff.patch`,
  one row of `results/runs.csv` (table); the dashboard renders both.
- Tool results are validated against Pydantic schemas on every call.

## 4. Agentic design patterns, evaluated against each other

| Pattern | Where |
|---|---|
| Sequential pipeline | `architectures/sequential.py` |
| Hierarchical / orchestrator-workers (manager LLM) | `architectures/hierarchical.py` |
| Event-driven | `architectures/event_driven.py` |
| Evaluator-optimizer loop (Critic → Strategist) | `pipeline.py` attempts |
| ReAct (tools chosen by the agent) | `prompt_style: react` |
| Reflection (draft → critique → revise) | `prompt_style: reflection` |
| Tool use / RAG | Strategist + ADK reviewer |

- **Evaluation:** E1 / E7 (architectures, with repeats), E3 (prompting
  patterns), E5 (ablations). Statistics: Friedman + Holm-corrected Wilcoxon
  (`experiments/analyze_results.py`).

## 5. Task monitoring and logging with callbacks

- **CrewAI callbacks:** `Agent.step_callback` (thoughts, tool calls, tool
  results) and `Task.callback` (task completion) feed the run's event log
  through a context-local monitor (`optiflow/core/llm.py`).
- **Pipeline event callback:** every step emits start/end events with
  intermediate outputs, timing, tokens, cost and errors
  (`Pipeline.emit`), streamed live over WebSocket and saved to
  `events.jsonl`.
- **ADK callbacks:** before/after model and tool callbacks log to
  `results/traces/adk_reviewer.jsonl`.
- Errors: failed steps are marked with status `error`; LLM retries and
  guardrail decisions are events too.
- **Tests:** `tests/test_monitoring.py`.
- **See it:** Run page → timeline + "Guardrails, A2A and framework callbacks".
- Note: in this CrewAI version, agents without tools answer in one step,
  so only tool-using (ReAct) agents produce step callbacks.

## 6. Agent-to-agent communication with A2A, across frameworks

- The **Verification Reviewer** is a **Google ADK** `LlmAgent`
  (`optiflow/interop/adk_reviewer.py`) published with ADK's `to_a2a`
  (`a2a_server.py`, agent card at `/.well-known/agent-card.json`).
- The **CrewAI** pipeline calls it with the official `a2a-sdk` client
  (`a2a_client.py`); token usage comes back in ADK's A2A metadata and is
  billed to the run.
- Selected per run with `critic_backend: adk_a2a`; in docker-compose the
  reviewer is its own service.
- **Evaluation:** E6 (`configs/e6_interop.yaml`): CrewAI critic vs ADK
  reviewer over A2A on the same programs.
- **Tests:** `tests/test_interop.py` (offline ADK agent over A2A; live
  test with `OPTIFLOW_LIVE_TESTS=1`).

## 7. CrewAI and ADK only

- Agent frameworks used: **CrewAI** (the seven-agent team) and **Google
  ADK** (the reviewer). Nothing else: LiteLLM-style model strings, MCP,
  A2A, ChromaDB, XGBoost, FastAPI are libraries/protocols, not agent
  frameworks.

## 8. Security: guardrails, validation callbacks, prompt variance

- **Guardrails** (`optiflow/security/guardrails.py`): prompt-injection and
  abuse detection on user guidance (API answers 422), program source
  (poisoned comments neutralized), and LLM output.
- **CrewAI task guardrails** on Strategist / Transformer / Critic /
  Analyzer output, with retries.
- **Validation callbacks:** tool returns type-checked (`validate_tool_output`);
  ADK `after_tool_callback` type-checks the reviewer's tool output.
- Plus: source safety filter, flag whitelist, sandbox, rule-based Critic,
  API write token for deployments.
- **Prompt variance:** prompt *architecture* (structured / ReAct /
  reflection / few-shot) and *content* via four personas
  (`agents/prompts/strategist.py`). Evaluated in E3.
- **Tests:** `tests/test_guardrails.py`, `tests/test_monitoring.py`.
- **See it:** Security page (layers, live tester, audit trail).

## 9. Observability, auditability, provenance

- OpenTelemetry: one trace file per run (`results/traces/<run_id>.jsonl`),
  spans for every agent step and every MCP tool call, with model, tokens,
  cost, status; guardrail and callback events attached as span events.
- Provenance: `report.json` (config, plans, diffs, verdicts, evidence),
  `events.jsonl`, `best.c`, `diff.patch`; the ADK side's own audit log.
- Metrics from traces: per-agent latency (mean/median/P95), cost share,
  critical path (`observability/metrics.py`). LLM judge for plan quality
  (`observability/judge.py`).

## 10. End-to-end evaluation: cost and running time over multiple runs

- Every run records tokens, USD cost and wall time; `runs.csv` aggregates.
- Configs E0-E7, resumable runner; E7 repeats each cell three times.
- Analysis: geometric-mean speedup, success with Wilson CI, mean / median /
  P95 cost and latency, Pareto front (`results/analysis.json`, figures).
- Prompt variance across architecture (ReAct vs few-shot vs structured vs
  reflection) and content (personas): E3.
- **See it:** Experiments and Agents pages. Measured numbers: `STATUS.md`.

## 11. Cloud deployment

- `Dockerfile`, `docker-compose.yml` (app + ADK reviewer as separate
  services over A2A), `deploy/README.md` (Google Compute Engine recipe),
  `deploy/vm-startup.sh`.
- A VM is required (the sandbox needs a Docker daemon), not serverless.
- Deploying needs a GCP account with billing; see `STATUS.md` for whether
  it has been deployed.
