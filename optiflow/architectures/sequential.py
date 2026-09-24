"""Sequential architecture: a fixed pipeline, looped in plain Python.

Lowest coordination overhead of the three architectures and the one the
rest of the system is validated against first (Section 16.1, week 3
milestone). Hierarchical and Event-Driven implement the same
Architecture interface and produce the same RunState shape.
"""

from __future__ import annotations

import uuid

from optiflow.agents import analyzer, benchmark, compiler_exec, critic, mcp_tools, profiler, strategist, transformer
from optiflow.architectures.base import Architecture, RunConfig
from optiflow.core.budget import RunBudget
from optiflow.core.schemas import Candidate, RunState
from optiflow.observability.tracing import get_tracer


class Sequential(Architecture):
    def run(self, program_id: str) -> RunState:
        state = RunState(
            run_id=uuid.uuid4().hex,
            program_id=program_id,
            architecture="sequential",
            messaging=self.cfg.messaging,
            budget_attempts=self.cfg.max_attempts,
        )
        tracer = get_tracer()
        budget = RunBudget(max_attempts=self.cfg.max_attempts, max_usd=self.cfg.max_usd_per_run)

        with tracer.start_as_current_span("run", attributes={"program": program_id, "architecture": "sequential"}):
            with mcp_tools.MCPServerAdapter(mcp_tools.SERVER_PARAMS) as tools:
                analyzer_agent = analyzer.make_agent(mcp_tools.tool_subset(tools, analyzer.TOOL_NAMES))
                profiler_agent = profiler.make_agent(mcp_tools.tool_subset(tools, profiler.TOOL_NAMES))
                strategist_agent = strategist.make_agent(self.cfg.prompt_style)
                transformer_agent = transformer.make_agent()
                compiler_exec_agent = compiler_exec.make_agent(
                    mcp_tools.tool_subset(tools, compiler_exec.TOOL_NAMES)
                )

                with tracer.start_as_current_span("agent.analyzer"):
                    state.summary = analyzer.run(analyzer_agent, program_id)
                self.channel.publish("analyzer", "summary", {"program_id": program_id})

                with tracer.start_as_current_span("agent.profiler"):
                    state.profile = profiler.run(profiler_agent, state.summary)
                self.channel.publish("profiler", "profile", {"bottleneck": state.profile.bottleneck_text})

                current_source = state.summary.source
                state.best = {
                    "candidate": Candidate(attempt=0, source=current_source, flags=["-O2"]).model_dump(),
                    "speedup": 1.0,
                }

                feedback = ""
                for attempt in range(1, self.cfg.max_attempts + 1):
                    with tracer.start_as_current_span("agent.strategist", attributes={"attempt": attempt}):
                        plan = strategist.run(
                            strategist_agent, state.summary, state.profile, state.history,
                            attempt, self.cfg.prompt_style,
                        )
                    self.channel.publish("strategist", "plan", {"attempt": attempt})

                    with tracer.start_as_current_span("agent.transformer", attributes={"attempt": attempt}):
                        candidate = transformer.run(
                            transformer_agent, state.best["candidate"]["source"],
                            state.summary.language, plan, feedback,
                        )
                    self.channel.publish("transformer", "candidate", {"attempt": attempt})

                    with tracer.start_as_current_span("agent.compiler_exec", attributes={"attempt": attempt}):
                        build, tests = compiler_exec.run(
                            compiler_exec_agent, candidate, state.summary.language, program_id
                        )

                    bench_result, compare_result = None, None
                    if build.ok and tests is not None and tests.all_pass:
                        with tracer.start_as_current_span("agent.benchmark", attributes={"attempt": attempt}):
                            bench_result, compare_result = benchmark.run(
                                build.candidate_id, program_id, n=self.cfg.bench_n
                            )

                    with tracer.start_as_current_span("agent.critic", attributes={"attempt": attempt}):
                        verdict = critic.decide(
                            build, tests, compare_result, budget,
                            current_best_speedup=state.best["speedup"],
                        )

                    state.history.append({
                        "attempt": attempt,
                        "plan": plan.model_dump(),
                        "candidate": candidate.model_dump(),
                        "bench": bench_result.model_dump() if bench_result else None,
                        "verdict": verdict.model_dump(),
                    })
                    self.channel.publish("critic", "verdict", {"attempt": attempt, "accepted": verdict.accepted})

                    if verdict.accepted and verdict.speedup > state.best["speedup"]:
                        state.best = {"candidate": candidate.model_dump(), "speedup": verdict.speedup}

                    feedback = verdict.feedback_for_strategist
                    if verdict.stop:
                        break

        return state
