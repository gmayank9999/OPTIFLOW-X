# OPTIFLOW-X

Measurement-driven multi-agent optimization of C/C++ programs.

OPTIFLOW-X takes a slow C/C++ program, profiles it, proposes source- and
flag-level optimizations through a set of specialized LLM agents, applies
them, and verifies every claim with real tools: the code has to compile, the
output has to match a reference exactly (or within tolerance), and the
speedup has to hold up under repeated, statistically checked timing runs.
Nothing is accepted on the model's word alone.

The project also runs as a small research study: the same optimization loop
is executed under different multi-agent architectures (sequential,
hierarchical, event-driven), messaging styles (blackboard, peer-to-peer,
broadcast) and prompting strategies, and the results are compared on
accuracy, latency and cost.

## Status

Actively being built. See the commit history for what exists today; this
README describes the target shape of the system, not a finished product.

## How it works, in one run

1. **Analyzer** reads the source and extracts loops, functions and static
   features with tree-sitter.
2. **Profiler** runs the baseline in a sandbox and collects timing and
   hardware counters (or a cachegrind/gprof fallback).
3. **Strategist** combines the profile, a small RAG knowledge base of
   compiler-optimization notes, and an XGBoost ranking model to propose one
   or two source-level transformations.
4. **Transformer** rewrites the source accordingly.
5. **Compiler & Executor** builds the candidate in a locked-down Docker
   sandbox, self-repairing compile errors up to twice.
6. **Benchmark** times the candidate: warm-up runs discarded, ten timed
   runs, median/P95/CV reported.
7. **Critic** applies a deterministic accept/reject rule (compile ok, tests
   pass, speedup >= 1.05 with p < 0.05) and either stops or sends feedback
   back to the Strategist for another attempt.

Every step is traced with OpenTelemetry so latency, token cost and the
critical path can be reconstructed after the fact.

## Repository layout

```
optiflow/
  core/           shared schemas, config, LLM/model routing, attempt budget
  tools/          sandbox runner, compiler, benchmark, verifier, profiler, analyzer
  mcp_server/     MCP tool server all agents call into
  agents/         the seven CrewAI agents and their prompts
  knowledge/      RAG ingestion and retrieval
  ml/             XGBoost strategy predictor
  comms/          blackboard / peer-to-peer / broadcast messaging
  architectures/  sequential / hierarchical / event-driven orchestration
  observability/  tracing, metrics, LLM-judge scoring
  experiments/    experiment matrix runner and analysis
  api/            FastAPI backend

benchmarks/       the C/C++ benchmark suite (source, inputs, expected outputs)
docker/           sandbox image definition
dashboard/        Next.js frontend
results/          run outputs, traces, figures (generated, not versioned)
tests/            test suite
```

## Setup

Requirements: Python 3.11 (CrewAI does not yet support 3.14), Docker
Desktop, Node 20+ for the dashboard.

```bash
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

docker build -t optiflow-sandbox -f docker/sandbox.Dockerfile .

copy .env.example .env
# fill in API keys for whichever LLM provider you're using
```

Run the sandbox/tooling tests:

```bash
pytest tests/
```

Regenerate benchmark reference outputs (only ever run once, before any
experiments start):

```bash
python benchmarks/make_expected.py
```

## Benchmark suite

50 deliberately unoptimized but correct C/C++ programs across matrix/linear
algebra, stencils, sorting/searching, graphs, dynamic programming, strings
and data layout, each with three test inputs and exact reference outputs.
A 10-program subset (`benchmarks/manifest.json`, `subset10: true`) is used
for the architecture/messaging/prompting experiments so those comparisons
stay affordable.

## License

Coursework project; no license granted for reuse.
