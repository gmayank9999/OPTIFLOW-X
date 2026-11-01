# Status

Last updated: 27 Oct 2026. This file says what is built, what has been
measured, and what hasn't, without rounding up.

## Built and tested

| Area | State |
|---|---|
| Sandbox | Docker, no network (outbound connect tested to fail), non-root, zero effective capabilities (tested), read-only root, memory/PID limits, timeout. `CAP_PERFMON` only for profiling the trusted baseline. |
| Correctness | Exit status + output on 3 inputs; ASan + UBSan build on the small inputs (tested to catch an out-of-bounds read that still prints the right checksum). |
| Timing | `hrtime` harness (ns wall clock, CPU time, peak RSS); binaries + input staged in tmpfs; baseline and candidates interleaved in one container; 10-30 runs depending on runtime; Mann-Whitney U. |
| Profiling | Real `perf stat` counters and `perf record` samples rolled up onto loops (hotspot = tightest loop holding the time). cachegrind / gprof fallbacks. |
| Static analysis | Every feature computed from the tree-sitter AST and scoped correctly (recursion = a function calling itself; mallocs only inside loops; strlen only in loop conditions; stride mismatch only in nested innermost loops). |
| Agents | 7 agents. Every sandbox access goes through one MCP stdio session. Token usage and USD cost metered per LLM call. Strategist sees the line-numbered source and real hotspots; malformed plans get one retry, then become a rejected attempt instead of a crash. |
| Critic | Deterministic accept/reject (compile, tests, sanitizers, >= 1.05x, p < 0.05, > 2% better than current best, not identical to current best); LLM only writes rejection feedback. Stop rules: budget, USD cap, diminishing returns, 3 rejects in a row. |
| Architectures | Sequential, Hierarchical (manager LLM with guardrails), Event-driven (event bus; profiling in parallel with analysis). All three tested end to end. |
| Messaging | Blackboard / peer-to-peer / broadcast. Steps read their inputs from the channel, so the mechanism changes what agents see. All three tested end to end. |
| Prompting | Structured, ReAct (RAG + predictor as real tools), reflection (draft, critique, revise). |
| Ablations | full, no_rag, no_xgb, llm_only, rule_only (no LLM), flags_only (no LLM). |
| Observability | One OpenTelemetry trace file per run with model/tokens/cost on agent spans; per-agent latency, P95, cost share, critical-path share. LLM judge with rubric + human-validation workflow. |
| Experiments | YAML configs E0-E5, resumable matrix runner, analysis (geo-mean, Wilson CI, Friedman + Holm-Wilcoxon, Pareto), figures. |
| Frameworks + A2A | The seven-agent team is CrewAI; the Verification Reviewer is a Google ADK agent served with `to_a2a` and called from CrewAI over A2A (a2a-sdk). Tested offline (deterministic ADK agent) and live (real Gemini tokens over A2A); a full optimization run with `critic_backend=adk_a2a` completed. |
| Guardrails | Injection/abuse scanning of user guidance (HTTP 422 with findings), program source (poisoned comments neutralized; zero false positives on the 50 programs) and LLM output; CrewAI task guardrails with retry on Strategist/Transformer/Critic/Analyzer; type-checked MCP tool returns; ADK before/after model and tool callbacks. |
| Monitoring | CrewAI step + task callbacks and guardrail decisions stream into each run's event log and trace (tool-free CrewAI agents answer in one step, so only tool-using agents produce step callbacks). |
| Prompt variance | structured / ReAct / reflection / few-shot, and four Strategist personas. |
| Deployment | Dockerfile (pinned to tested versions) + docker-compose (app and ADK reviewer as separate services over A2A) + GCP guide. Verified locally with docker compose: a run through the stack was accepted at 258x and the app reached the reviewer over A2A across containers. Not yet deployed to a cloud account. |
| Dashboard | Next.js static export served by the API: overview, live run view (trace timeline over WebSocket, receipts, timing strip plots, diffs), programs with perf heat gutter, agents, experiments, predictor, method. Light/dark. |
| Tests | 130+ tests; `tests/test_architectures.py` runs all three architectures for real with a scripted LLM stand-in. |

## Measured on this machine

Machine: Intel i7-1185G7 laptop, Windows 11, Docker Desktop on WSL2
(`results/machine.json`). This is a noisy place to time code; see below.

- **Stability** (10 runs x 2 sessions, all 50 programs, machine otherwise
  undisturbed): 32/50 programs have within-session CV < 3%, 41/50 < 5%.
  38/50 baselines run 0.3-5 s at -O2; 12 are shorter (parse-bound graph/DP
  programs, plus two ~20 ms programs where GCC already hoists the
  redundant work). Short programs get up to 30 timed runs.
- **Wall vs CPU time**: under background load both clocks show the same CV,
  i.e. the noise is CPU speed variation, not descheduling. Wall time is
  kept (as the plan specifies); interleaving is what protects comparisons.
- **First live LLM run** (matmul, sequential, Gemini flash-lite): loop
  interchange accepted at 4.89x, then tiling on top at 7.69x; 6 LLM calls,
  9.2k tokens, $0.0013.
- **Strategy sweep** (`results/ml_sweep_detail.json`, all 50 programs, no
  LLM): -O3 alone barely moves the cache-bound programs (matmul ~1.0x,
  frobenius ~1.0x) while a hand-written loop interchange gives 2.4-3.4x;
  algorithmic rewrites give 30-2000x on the quadratic/exponential
  programs; clang -O3 is *slower* than gcc -O2 on some (rod_cutting
  0.56x). `-O3 -march=native` *fails the exact-output test* on mandelbrot
  (FMA contraction changes rounding), which the verifier catches.
- **Strategy predictor** (`results/xgb_report.json`): 77 labels, 52
  positive. Only `flags` has enough labels to train on, and its
  leave-one-program-out AUC is 0.52 -- the static features cannot predict
  whether -O3 helps. No strategy earned a model, so the predictor runs on
  the static heuristic. Heuristic top-3 hit rate 97% vs 84% for a naive
  "flags, interchange, tiling" list, but top-1 is 63% vs 71% for "always
  flags". Caveat: the heuristic and the templates were written from the
  same domain knowledge, so its top-3 rate is partly circular; the
  ablations (no_xgb) are the fair test of whether the prior helps.

- **E0 baselines, no LLM, all 50 programs**: flags only (-O3
  -march=native) improves 19/50 programs, geo-mean 1.21x; the rule-based
  baseline (predictor + hand-written templates) improves 36/50, geo-mean
  4.60x.
- **E1 architecture, 10-program subset, 1 run per cell, Gemini
  flash-lite** (`results/analysis.json`):

  | Architecture | Geo-mean | Success | Cost/run | Latency | Attempts |
  |---|---|---|---|---|---|
  | Sequential | 9.54x | 90% | $0.0030 | 113 s | 4.5 |
  | Hierarchical | 6.24x | 80% | $0.0028 | 112 s | 3.6 |
  | Event-driven | 6.04x | 90% | $0.0030 | 85 s | 4.4 |

  Friedman p = 0.013; sequential beats both others in Holm-corrected
  Wilcoxon tests, but by a median of only 6-9% per program, and most of
  the geo-mean gap is one program (particles_aos 55x vs ~5x) where one LLM
  attempt found a much better rewrite. With one run per cell this is
  well within what LLM randomness could produce; it needs repeats before
  it means anything. What does match the designs: event-driven is ~25%
  faster (profiling overlaps analysis) and the hierarchical manager
  stops earliest and spends least.
- **E6 critic framework, 10-program subset, 1 run per cell, same Gemini
  model**: rejection feedback written by the in-process CrewAI critic vs a
  Google ADK agent reached over the A2A protocol.

  | Critic | Geo-mean | Success | Cost/run | Latency | Attempts | A2A calls |
  |---|---|---|---|---|---|---|
  | CrewAI (in-process) | 6.94x | 9/10 | $0.0029 | 114 s | 4.6 | - |
  | ADK over A2A | 7.01x | 9/10 | $0.0029 | 101 s | 4.1 | 20 (0 errors) |

  Wilcoxon on log-speedups p = 0.73, median ratio 1.02x: **no measurable
  difference in outcome**, which is what you would expect because the
  critic only rewrites feedback after a rejection; the verdict is
  rule-based either way. The A2A hop costs about 2.3 s per call. Per-program
  differences (e.g. lcs 1.66x vs 3.31x, floyd_warshall 3.15x vs 1.15x) are
  LLM run-to-run randomness at one run per cell, not a framework effect.
  The result shows the cross-framework path works end to end and costs
  little, not that either framework gives better feedback. Run with the
  statistical vs-best acceptance rule.

## Not done yet / limitations

- **LLM quota:** both Gemini keys used so far are free tier: 500
  requests/day per model and 15 requests/minute. The first key ran out
  of its daily quota during the first attempt at E6. The second key hit the
  per-minute limit (the retry now waits as long as the provider asks, see
  `core/llm.py`). The runner stops cleanly on a daily quota and resumes where
  it stopped: `python -m optiflow.experiments.run_all`. On a free tier the
  remaining experiments take roughly 1-2 weeks at ~25 runs/day; enabling
  billing finishes them in a few hours for about $1 at the measured cost per
  run. **Experiment status (1 Nov 2026, 08:50): E0 (100 runs), E1 (30) and
  E6 (20) are done. E3 is 14 of 70 cells done (the 10 structured-prompt
  baseline cells and 4 ReAct cells); the second key's 500-request daily quota
  then ran out and the runner stopped cleanly. E2, E5 and E7 have not
  started. Total LLM spend so far: $0.195. To continue: wait for the quota
  to reset (or enable billing), then run
  `python -m optiflow.experiments.run_all`. E4 (local / mixed models) is
  not run: it needs a 7B local model, which would swap on this 15 GB laptop
  and distort timings, and an OpenAI key.** The E3 comparison is not
  reported yet because most of its cells do not exist.
- **Very fast candidates make speedup ratios imprecise (acceptance logic
  fixed, ratios still imprecise).** A live bubble_sort run went 189x then
  234x (adding -flto). Those candidates run in about 5 ms with 31-34%
  run-to-run variation, where process startup dominates, so the
  189x -> 234x "improvement" was within noise. The Critic used to compare a
  candidate with the current best only by point estimate. Now the current
  best is timed in the same interleaved session as each new candidate and
  "better than the best so far" must be significant (Mann-Whitney p < 0.05
  and >= 1.02x). Runs from E0 and E1 predate this rule; E6 onward use it.
  Candidates under 20 ms or with CV > 25% are flagged "low timing
  precision" in the dashboard: treat ratios above ~100x as "much faster",
  not as precise numbers.
- **Cloud:** everything is ready (`deploy/README.md`) but deploying needs
  a GCP account with billing and the commits pushed to GitHub.

- E1 on all 50 programs, E2-E5, and repeats have not been run. The
  runner is resumable, so this is a matter of machine time and API budget.
- Two E1 runs were lost to a DNS outage before LLM calls
  had retry/backoff; they were re-run.
- Timing on a laptop under WSL2 is noisier than the plan's target (CV < 3%
  for all programs). A quiet Linux machine with pinned cores would do
  better; the protocol does not need to change.
- `single-local` and `mixed` model assignments need Ollama (and the mixed
  config an OpenAI key); only `single-cloud` (Gemini) has been exercised.
- The strategy predictor is trained on a small dataset by design (one row
  per program); `results/xgb_report.json` says which strategies earned a
  model and which fall back to the heuristic.
- The LLM judge has not been validated against human scores yet
  (`python -m optiflow.observability.judge export-human 30`).
