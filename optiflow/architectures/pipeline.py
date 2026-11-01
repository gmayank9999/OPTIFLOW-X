"""The optimization steps every architecture drives.

One Pipeline per run. Each step:
  - reads its inputs *from the channel*, as the agent that owns the step
    (so what an agent can see depends on the messaging mechanism),
  - runs the agent (LLM and/or MCP tools),
  - posts its output back to the channel,
  - is wrapped in an OpenTelemetry span carrying model, tokens and cost,
  - emits start/end events for the live dashboard stream.

Architectures differ only in *which step runs next* -- see sequential.py,
hierarchical.py and event_driven.py. Failures inside an attempt
(unparseable plan, unsafe rewrite, tool error) become a rejected attempt
with a reason, never a crashed run. (The Critic's decision uses the
attempt's own evidence objects; those same objects were posted to the
channel by the steps that produced them.)
"""

from __future__ import annotations

import json
import threading
import time
import traceback
import uuid
from contextlib import contextmanager

from optiflow.agents import analyzer, benchmark, compiler_exec, critic, profiler, strategist, transformer
from optiflow.agents.common import CandidateRejected, PlanError
from optiflow.agents.mcp_tools import ToolClient, ToolError
from optiflow.architectures.base import EventSink, RunConfig
from optiflow.comms.base import Channel
from optiflow.core import llm
from optiflow.core.budget import RunBudget
from optiflow.core.config import model_for
from optiflow.core.schemas import (
    BuildResult, Candidate, CompareResult, OptimizationPlan, ProfileReport, ProgramSummary,
    RunState, Strategy, TestResult, TokenUsage, Verdict,
)
from optiflow.observability.tracing import run_tracer

LLM_ROLES = ("analyzer", "profiler", "strategist", "transformer", "compiler_exec", "critic", "manager")
RULE_FLAGS = ["-O3", "-march=native"]


class Pipeline:
    def __init__(self, cfg: RunConfig, channel: Channel, tools: ToolClient, program_id: str,
                 architecture: str, emit: EventSink | None = None) -> None:
        self.cfg = cfg
        self.channel = channel
        self.tools = tools
        self.state = RunState(
            run_id=cfg.run_id or uuid.uuid4().hex,
            program_id=program_id,
            architecture=architecture,
            messaging=channel.name,
            prompt_style=cfg.prompt_style,
            model_assignment=cfg.model_assignment,
            variant=cfg.variant,
            persona=cfg.persona,
            critic_backend=cfg.critic_backend,
            instructions=cfg.instructions,
            budget_attempts=cfg.max_attempts,
            started_at=time.time(),
        )
        self.budget = RunBudget(max_attempts=cfg.max_attempts, max_usd=cfg.max_usd_per_run)
        self.tracer = run_tracer(self.state.run_id)
        self.events: list[dict] = []
        self._emit_fn = emit
        self._agents: dict = {}
        self._lock = threading.RLock()
        self._my_plans: list[dict] = []  # Strategist-local memory of its own plans
        self.meta: dict = {}
        self._templates_tried: set[str] = set()
        self.extra_stats: dict = {}  # architecture-specific counters, saved with the run

    # ------------------------------------------------------------------ infra

    def emit(self, type_: str, notify: bool = True, **data) -> dict:
        event = {"type": type_, "t": time.time(), "run_id": self.state.run_id, **data}
        with self._lock:
            self.events.append(event)
        if notify:
            self._notify(event)
        return event

    def _notify(self, event: dict) -> None:
        if self._emit_fn is not None:
            try:
                self._emit_fn(event)
            except Exception:  # noqa: BLE001 - a broken UI stream must not break a run
                pass

    def llm_enabled(self, role: str) -> bool:
        return self.cfg.uses_llm and role in LLM_ROLES

    def agent(self, role: str):
        if not self.llm_enabled(role):
            return None
        with self._lock:
            if role not in self._agents:
                module = {
                    "analyzer": analyzer, "profiler": profiler, "transformer": transformer,
                    "compiler_exec": compiler_exec, "critic": critic,
                }[role]
                self._agents[role] = module.make_agent(self.cfg.model_assignment)
            return self._agents[role]

    @contextmanager
    def step(self, agent_name: str, attempt: int | None = None, **attrs):
        """Span + events + usage accounting around one agent step.

        The body fills `rec`: rec["usage"] (TokenUsage), rec["summary"]
        (one line for the timeline), rec["data"] (small payload for the UI).
        """
        rec: dict = {"usage": TokenUsage(), "summary": "", "data": {}, "model": None}
        model = model_for(agent_name, self.cfg.model_assignment) if self.llm_enabled(agent_name) else "none"
        if agent_name == "critic" and self.cfg.critic_backend == "adk_a2a" and self.cfg.uses_llm:
            model = "adk:verification_reviewer via a2a"
        span_attrs = {
            "agent": agent_name, "model": model, "arch": self.state.architecture,
            "messaging": self.state.messaging, "variant": self.cfg.variant,
            "program": self.state.program_id, **({"attempt": attempt} if attempt is not None else {}),
            **attrs,
        }
        t0 = time.time()
        self.emit("step_start", agent=agent_name, attempt=attempt)
        def on_framework_event(event: dict) -> None:
            # CrewAI step/task callbacks and guardrail decisions for this step.
            if event.get("kind") == "guardrail" and not event.get("ok", True):
                self.record_guardrail(agent_name, attempt, event.get("stage", ""), event.get("detail", ""))
            self.emit("agent_event", agent=agent_name, attempt=attempt, **event)
            span.add_event(event.get("kind", "event"), {k: str(v)[:300] for k, v in event.items()})

        with self.tracer.start_as_current_span(f"agent.{agent_name}", attributes=span_attrs) as span, \
                llm.monitor(on_framework_event):
            status = "ok"
            try:
                yield rec
            except Exception as exc:
                status = "error"
                rec["summary"] = rec["summary"] or f"{type(exc).__name__}: {str(exc)[:200]}"
                raise
            finally:
                usage: TokenUsage = rec["usage"]
                self._account(agent_name, usage)
                span.set_attributes({
                    "tokens_in": usage.prompt_tokens, "tokens_out": usage.completion_tokens,
                    "llm_calls": usage.calls if usage.prompt_tokens or usage.completion_tokens else 0,
                    "cost_usd": usage.cost_usd, "status": status,
                })
                self.emit(
                    "step_end", agent=agent_name, attempt=attempt, status=status,
                    dur_ms=(time.time() - t0) * 1000, summary=rec["summary"], data=rec["data"],
                    tokens_in=usage.prompt_tokens, tokens_out=usage.completion_tokens,
                    cost_usd=usage.cost_usd, model=model,
                )

    def record_guardrail(self, agent: str, attempt: int | None, stage: str, detail: str) -> None:
        event = {"agent": agent, "attempt": attempt, "stage": stage, "detail": str(detail)[:400], "t": time.time()}
        with self._lock:
            self.state.guardrail_events.append(event)
            self.extra_stats["guardrail_flags"] = self.extra_stats.get("guardrail_flags", 0) + 1
        self.emit("guardrail", **{k: v for k, v in event.items() if k != "t"})

    def _account(self, agent_name: str, usage: TokenUsage) -> None:
        with self._lock:
            self.state.usage.add(usage)
            self.state.usage_by_agent.setdefault(agent_name, TokenUsage()).add(usage)
            self.budget.record_call(usage.cost_usd)

    def call_tool(self, name: str, **kwargs) -> dict:
        with self.tracer.start_as_current_span(f"tool.{name}", attributes={"tool": name, "transport": self.tools.transport}):
            return self.tools.call(name, **kwargs)

    def _read(self, agent: str, topic: str) -> dict:
        payload = self.channel.latest(agent, topic)
        if payload is None:
            raise MissingContext(f"{agent} never received '{topic}' ({self.channel.name})")
        return payload

    # ----------------------------------------------------------------- steps

    def analyze(self) -> ProgramSummary:
        with self.step("analyzer") as rec:
            summary, rec["usage"] = analyzer.run(self.agent("analyzer"), _TracedTools(self), self.state.program_id)
            self.meta = self.call_tool("get_program", program_id=self.state.program_id)["meta"]
            rec["summary"] = summary.summary_text[:300]
            rec["data"] = {"features": summary.features, "loops": len(summary.loops)}
        self.state.summary = summary
        for finding in summary.guardrail_findings:
            self.record_guardrail("analyzer", None, f"program_source:{finding['rule']}", finding["excerpt"])
        if self.state.best is not None:
            self.ensure_best_source()
        self.channel.post("analyzer", "summary", summary.model_dump())
        return summary

    def measure_profile(self) -> ProfileReport:
        """Tool-only half of profiling: needs nothing but the program id."""
        return profiler.measure(_TracedTools(self), self.state.program_id)

    def profile(self, measured: ProfileReport | None = None) -> ProfileReport:
        with self.step("profiler") as rec:
            summary = ProgramSummary(**self._read("profiler", "summary"))
            report = measured or self.measure_profile()
            report, rec["usage"] = profiler.interpret(self.agent("profiler"), report, summary)
            rec["summary"] = report.bottleneck_text[:300]
            rec["data"] = {
                "baseline_ms": report.baseline_runtime_ms, "ipc": report.ipc,
                "l1_miss_rate": report.l1_miss_rate, "llc_miss_rate": report.llc_miss_rate,
                "hotspots": [h.model_dump() for h in report.hotspots], "source": report.counters_source,
            }
        self.state.profile = report
        self.channel.post("profiler", "profile", report.model_dump())
        return report

    def start(self) -> None:
        self.state.best = {
            "candidate": Candidate(attempt=0, source="", flags=["-O2"]).model_dump(),
            "speedup": 1.0,
            "attempt": 0,
        }
        self.emit("run_start", program_id=self.state.program_id, config=_cfg_dict(self.cfg),
                  architecture=self.state.architecture)

    def ensure_best_source(self) -> None:
        if not self.state.best["candidate"]["source"]:
            self.state.best["candidate"]["source"] = self.state.summary.source

    def plan(self, attempt: int) -> OptimizationPlan:
        with self.step("strategist", attempt=attempt, prompt_style=self.cfg.prompt_style) as rec:
            if not self.cfg.uses_llm:
                plan = self._rule_plan(attempt)
            else:
                summary = ProgramSummary(**self._read("strategist", "summary"))
                profile = ProfileReport(**self._read("strategist", "profile"))
                context = strategist.build_context(
                    summary, profile,
                    best_source=self.state.best["candidate"]["source"] or summary.source,
                    best_speedup=self.state.best["speedup"],
                    best_flags=self.state.best["candidate"]["flags"],
                    compare_mode=self.meta.get("compare", "exact"),
                    history_compact=self._strategist_history(),
                    shared_context=self._shared_context("strategist"),
                    use_rag=self.cfg.variant not in ("no_rag", "llm_only"),
                    use_xgb=self.cfg.variant not in ("no_xgb", "llm_only"),
                    instructions=self.cfg.instructions,
                    persona=self.cfg.persona,
                )
                plan, rec["usage"], info = strategist.plan(
                    self.cfg.model_assignment, context, attempt, self.cfg.prompt_style
                )
                rec["data"]["persona"] = self.cfg.persona
                rec["data"]["prompt_chars"] = info.get("prompt_chars")
                rec["data"]["tool_calls"] = info.get("tool_calls", [])
            rec["summary"] = _plan_line(plan)
            rec["data"]["plan"] = plan.model_dump()
        self._my_plans.append(plan.model_dump())
        self.channel.post("strategist", "plan", plan.model_dump())
        return plan

    def transform(self, plan: OptimizationPlan, feedback: str = "") -> Candidate:
        with self.step("transformer", attempt=plan.attempt) as rec:
            plan = OptimizationPlan(**self._read("transformer", "plan"))
            parent = self.state.best["candidate"]
            flags = plan.flags if plan.flags and plan.flags != ["-O2"] else parent["flags"]
            if not self.cfg.uses_llm:
                candidate = self._rule_transform(plan, parent["source"], flags)
            else:
                candidate, rec["usage"] = transformer.run(
                    self.agent("transformer"), parent["source"], self.state.summary.language,
                    plan, flags, feedback=feedback, compare_mode=self.meta.get("compare", "exact"),
                    tolerance=float(self.meta.get("tolerance", 0.0) or 0.0),
                )
            rec["summary"] = f"{_diff_stats(candidate.diff)} | flags {' '.join(candidate.flags)}"
            rec["data"] = {"diff": candidate.diff[:20000], "flags": candidate.flags}
        self.channel.post("transformer", "candidate", candidate.model_dump())
        return candidate

    def build_and_test(self, attempt: int) -> tuple[Candidate, BuildResult, TestResult | None]:
        with self.step("compiler_exec", attempt=attempt) as rec:
            candidate = Candidate(**self._read("compiler_exec", "candidate"))
            candidate, build, tests, rec["usage"] = compiler_exec.run(
                self.agent("compiler_exec"), _TracedTools(self), candidate,
                parent_source=self.state.best["candidate"]["source"],
                lang=self.state.summary.language, program_id=self.state.program_id,
                allow_unsafe_math=self.meta.get("compare") == "float_tol",
            )
            if not build.ok:
                rec["summary"] = "compile failed" + (f" after {candidate.repaired} repair(s)" if candidate.repaired else "")
            elif tests is not None:
                passed = sum(1 for d in tests.details.values() if d.get("matched"))
                rec["summary"] = (f"compiled ({' '.join(build.flags)}); tests {passed}/{len(tests.details)}"
                                  f"; sanitizer {'ok' if tests.sanitizer_ok else ('FAIL' if tests.sanitizer_ok is False else 'n/a')}")
            rec["data"] = {
                "ok": build.ok, "repaired": candidate.repaired, "dropped_flags": build.dropped_flags,
                "stderr": build.stderr[-1500:] if not build.ok else "",
                "tests": tests.model_dump(exclude={"sanitizer_report"}) if tests else None,
            }
        self.channel.post("compiler_exec", "build", {"attempt": attempt, **build.model_dump()})
        if tests is not None:
            self.channel.post("compiler_exec", "tests", {"attempt": attempt, **tests.model_dump()})
        return candidate, build, tests

    def benchmark(self, attempt: int) -> CompareResult | None:
        build = BuildResult(**{k: v for k, v in self._read("benchmark", "build").items() if k != "attempt"})
        tests = self.channel.latest("benchmark", "tests")
        if not build.ok or tests is None or not tests.get("all_pass") or tests.get("attempt") != attempt:
            return None
        with self.step("benchmark", attempt=attempt) as rec:
            result = benchmark.run(_TracedTools(self), build.candidate_id, self.state.program_id, self.cfg.bench_n,
                                   reference_id=self.state.best.get("candidate_id"))
            vs_best = (f", {result.vs_best_speedup:.2f}x vs best (p={result.vs_best_p_value:.3f})"
                       if result.vs_best_p_value is not None else "")
            rec["summary"] = (f"{result.speedup:.2f}x wall, {result.cpu_speedup:.2f}x cpu, p={result.p_value:.4f}"
                              f"{vs_best} ({result.candidate.median_ms:.1f} vs {result.baseline.median_ms:.1f} ms)"
                              f"{' [low precision]' if result.low_precision else ''}"
                              if result.candidate and result.baseline else "no measurement")
            rec["data"] = {
                "speedup": result.speedup, "cpu_speedup": result.cpu_speedup, "p_value": result.p_value,
                "vs_best_speedup": result.vs_best_speedup, "vs_best_p_value": result.vs_best_p_value,
                "low_precision": result.low_precision,
                "baseline": result.baseline.model_dump() if result.baseline else None,
                "candidate": result.candidate.model_dump() if result.candidate else None,
            }
        self.channel.post("benchmark", "compare", {"attempt": attempt, **result.model_dump()})
        return result

    def judge(self, attempt: int, plan: OptimizationPlan | None, candidate: Candidate | None,
              build: BuildResult | None, tests: TestResult | None, compare: CompareResult | None,
              rejected: tuple[str, str] | None = None) -> Verdict:
        with self.step("critic", attempt=attempt) as rec:
            verdict = critic.decide(
                build or BuildResult(ok=False), tests, compare, self.budget,
                current_best_speedup=self.state.best["speedup"],
                rejected_reason=rejected[0] if rejected else None,
                rejected_detail=rejected[1] if rejected else "",
            )
            if not verdict.accepted and self.llm_enabled("critic") and rejected is None:
                plan_line = _plan_line(plan) if plan else "?"
                diff = candidate.diff if candidate else ""
                if self.cfg.critic_backend == "adk_a2a":
                    verdict, rec["usage"], rec["data"]["a2a"] = self._explain_via_a2a(verdict, plan_line, diff)
                else:
                    verdict, rec["usage"] = critic.explain(self.agent("critic"), verdict, plan_line, diff)
                # explain() may have pushed spend over the cap
                if not verdict.stop and self.budget.stop_reason():
                    verdict = verdict.model_copy(update={"stop": True, "stop_reason": self.budget.stop_reason()})
            rec["summary"] = ("ACCEPT " + f"{verdict.speedup:.2f}x") if verdict.accepted else f"REJECT {verdict.reason}"
            rec["data"] = {**verdict.model_dump(), **({"a2a": rec["data"]["a2a"]} if "a2a" in rec["data"] else {})}

        self.state.history.append({
            "attempt": attempt,
            "plan": plan.model_dump() if plan else None,
            "candidate": candidate.model_dump() if candidate else None,
            "build": build.model_dump() if build else None,
            "tests": tests.model_dump() if tests else None,
            "compare": compare.model_dump() if compare else None,
            "verdict": verdict.model_dump(),
        })
        if verdict.accepted and candidate is not None:
            self.state.best = {
                "candidate": candidate.model_dump(), "speedup": verdict.speedup, "attempt": attempt,
                "candidate_id": build.candidate_id if build else None,  # reference for the next attempt's test
                "compare": compare.model_dump() if compare else None,
                "strategies": [s.name for s in plan.strategies] if plan else [],
            }
        self.channel.post("critic", "verdict", {"attempt": attempt, **verdict.model_dump()})
        self.emit("attempt_end", attempt=attempt, verdict=verdict.model_dump(),
                  best_speedup=self.state.best["speedup"])
        _log_experience(self.state, plan, verdict)
        return verdict

    # ------------------------------------------------------------- attempts

    def attempt(self, attempt: int, plan: OptimizationPlan | None = None, feedback: str = "") -> Verdict | None:
        """plan -> transform -> build/test -> benchmark -> judge, with every
        failure mode mapped to a rejected verdict. Returns None when an
        LLM-free baseline has nothing left to try (no attempt was made)."""
        candidate = build = tests = compare = None
        try:
            if plan is None:
                plan = self.plan(attempt)
            else:
                plan = plan.model_copy(update={"attempt": attempt})
                self.channel.post("strategist", "plan", plan.model_dump())
            candidate = self.transform(plan, feedback)
            parent = self.state.best["candidate"]
            if candidate.source.strip() == parent["source"].strip() and candidate.flags == parent["flags"]:
                raise CandidateRejected("no_change", "the candidate is identical to the current best (source and flags)")
            candidate, build, tests = self.build_and_test(attempt)
            compare = self.benchmark(attempt)
            return self.judge(attempt, plan, candidate, build, tests, compare)
        except PlanError as exc:
            return self.judge(attempt, plan, None, None, None, None, rejected=("plan_error", str(exc)[:500]))
        except CandidateRejected as exc:
            return self.judge(attempt, plan, candidate, None, None, None, rejected=(exc.reason, exc.detail))
        except NoMoreRules:
            return None
        except (ToolError, MissingContext) as exc:
            return self.judge(attempt, plan, candidate, build, tests, None,
                              rejected=(type(exc).__name__.lower(), str(exc)[:500]))

    def _explain_via_a2a(self, verdict: Verdict, plan_line: str, diff: str):
        """Rejection feedback from the Google ADK reviewer over A2A. Same
        prompt and output guardrail as the in-process CrewAI critic, so the
        two backends are directly comparable. A transport failure keeps the
        rule-based evidence (never blocks the run) and is recorded."""
        from optiflow.interop.a2a_client import A2AError, local_reviewer

        try:
            client = local_reviewer()
            text, usage, info = client.review(critic.feedback_prompt(verdict, plan_line, diff))
        except A2AError as exc:
            self.extra_stats["a2a_errors"] = self.extra_stats.get("a2a_errors", 0) + 1
            return verdict, TokenUsage(), {"error": str(exc)[:300]}
        self.extra_stats["a2a_calls"] = self.extra_stats.get("a2a_calls", 0) + 1
        self.extra_stats["a2a_latency_ms"] = self.extra_stats.get("a2a_latency_ms", 0.0) + info["latency_ms"]
        ok, why = critic.clean_feedback(text)
        if not ok or "blocked by the input guardrail" in text or "withheld by the output guardrail" in text:
            self.record_guardrail("critic", None, "a2a_reply", why if not ok else text[:200])
            return verdict, usage, {**info, "guardrail": "blocked"}
        return critic.with_feedback(verdict, text), usage, info

    def finish(self, stop_reason: str = "", error: str = "") -> RunState:
        self.state.stop_reason = stop_reason or self.budget.stop_reason() or "completed"
        self.state.error = error
        self.state.messaging_stats = {**self.channel.stats(), **self.extra_stats}
        self.state.finished_at = time.time()
        if self.state.best and not self.state.best["candidate"]["source"] and self.state.summary:
            self.state.best["candidate"]["source"] = self.state.summary.source
        from optiflow.experiments.store import save_run

        # run_end goes into the persisted log (the timeline needs the end
        # time), but live listeners hear about it only *after* the report is
        # on disk -- otherwise a client reloading on run_end finds nothing.
        end = self.emit("run_end", notify=False, status="failed" if error else "done",
                        stop_reason=self.state.stop_reason,
                        best_speedup=self.state.best["speedup"] if self.state.best else 1.0,
                        usage=self.state.usage.model_dump(), messaging=self.state.messaging_stats, error=error)
        save_run(self.state, self.cfg, self.events)
        self._notify(end)
        return self.state

    def fail(self, exc: BaseException) -> RunState:
        return self.finish("error", error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-2000:]}")

    # ------------------------------------------------- context for the LLM

    def _strategist_history(self) -> str:
        """Own plans (agent-local memory) joined with the verdicts this agent
        actually received over the channel."""
        verdicts = {m.payload.get("attempt"): m.payload for m in self.channel.read("strategist", "verdict")}
        lines = []
        for p in self._my_plans:
            v = verdicts.get(p["attempt"])
            names = "+".join(s["name"] for s in p["strategies"])
            flags = " ".join(p.get("flags", []))
            if v is None:
                lines.append(f"A{p['attempt']} {names} [{flags}] -> (no verdict received)")
            elif v.get("accepted"):
                lines.append(f"A{p['attempt']} {names} [{flags}] -> ACCEPT {v['speedup']:.2f}x")
            else:
                lines.append(f"A{p['attempt']} {names} [{flags}] -> REJECT {v['feedback_for_strategist'][:400]}")
        return "\n".join(lines)

    def _shared_context(self, agent: str) -> str:
        """Extra evidence beyond verdicts, which depends on the mechanism:
        blackboard pulls the measurement topics it needs; broadcast must
        process its whole inbox; peer-to-peer gets nothing extra."""
        if self.channel.name == "p2p":
            return ""
        if self.channel.name == "blackboard":
            messages = [m for t in ("build", "tests", "compare") for m in self.channel.read(agent, t)]
        else:
            seen_topics = {"summary", "profile"}  # already in the prompt in full
            messages = [m for m in self.channel.read(agent) if m.topic not in seen_topics]
        messages.sort(key=lambda m: m.seq)
        return "\n".join(_render(m) for m in messages[-24:])

    # ---------------------------------------------------- LLM-free variants

    def _rule_plan(self, attempt: int) -> OptimizationPlan:
        """rule_only: walk the predictor's ranking and take the first strategy
        with a hand-written template for this program (or flags).
        flags_only: -O3 -march=native once."""
        if self.cfg.variant == "flags_only":
            if attempt > 1:
                raise NoMoreRules("flags-only baseline has a single attempt")
            return OptimizationPlan(attempt=attempt, flags=list(RULE_FLAGS),
                                    strategies=[Strategy(name="flags", rationale="flags-only baseline", confidence=1.0)])
        from optiflow.ml.predictor import rank
        from optiflow.ml.templates import TEMPLATES

        templates = TEMPLATES.get(self.state.program_id, {})
        for name, score in rank(self.state.summary.features, top_k=11):
            if name in self._templates_tried:
                continue
            if name == "flags" or name in templates:
                self._templates_tried.add(name)
                return OptimizationPlan(
                    attempt=attempt, flags=list(RULE_FLAGS) if name == "flags" else ["-O2"],
                    strategies=[Strategy(name=name, confidence=score, rationale="top-ranked strategy with a template")],
                )
        raise NoMoreRules("no untried strategy with a template")

    def _rule_transform(self, plan: OptimizationPlan, parent_source: str, flags: list[str]) -> Candidate:
        from optiflow.agents.codeblock import unified_diff
        from optiflow.ml.templates import TEMPLATES

        name = plan.strategies[0].name
        source = TEMPLATES.get(self.state.program_id, {}).get(name, parent_source) if name != "flags" else parent_source
        source = source.lstrip("\n")
        return Candidate(attempt=plan.attempt, source=source, flags=flags,
                         diff=unified_diff(parent_source, source))


class MissingContext(RuntimeError):
    """An agent needed a topic the channel never delivered to it."""


class NoMoreRules(RuntimeError):
    pass


class _TracedTools(ToolClient):
    """ToolClient that wraps every MCP call in a tool.<name> span."""

    def __init__(self, pipeline: Pipeline) -> None:
        self._p = pipeline
        self.transport = pipeline.tools.transport

    def call(self, name: str, **kwargs) -> dict:
        return self._p.call_tool(name, **kwargs)


def _cfg_dict(cfg: RunConfig) -> dict:
    return {k: v for k, v in cfg.__dict__.items() if k != "tags"}


def _plan_line(plan: OptimizationPlan) -> str:
    parts = []
    for s in plan.strategies:
        target = f"@{s.target}" if s.target else ""
        params = f"{json.dumps(s.params)}" if s.params else ""
        parts.append(f"{s.name}{target}{params}")
    return " + ".join(parts) + f" [{' '.join(plan.flags)}]"


def _diff_stats(diff: str) -> str:
    added = sum(1 for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff.splitlines() if l.startswith("-") and not l.startswith("---"))
    return f"+{added} -{removed} lines"


def _render(m) -> str:
    p = m.payload
    a = p.get("attempt", "?")
    if m.topic == "build":
        if p.get("ok"):
            dropped = f", dropped {p['dropped_flags']}" if p.get("dropped_flags") else ""
            return f"A{a} build ok with {' '.join(p.get('flags', []))}{dropped}"
        first = next((l for l in p.get("stderr", "").splitlines() if "error" in l), "")
        return f"A{a} build FAILED: {first[:200]}"
    if m.topic == "tests":
        statuses = ", ".join(f"{k.split('/')[-1]}={v.get('status')}" for k, v in p.get("details", {}).items())
        san = p.get("sanitizer_ok")
        return f"A{a} tests: {statuses}; sanitizer={'ok' if san else ('FAIL' if san is False else 'n/a')}"
    if m.topic == "compare":
        b, c = p.get("baseline") or {}, p.get("candidate") or {}
        return (f"A{a} timing: {p.get('speedup', 0):.2f}x wall / {p.get('cpu_speedup', 0):.2f}x cpu, "
                f"p={p.get('p_value', 1):.4f}, cand {c.get('median_ms', 0):.1f}ms "
                f"(cv {c.get('cv', 0):.3f}) vs base {b.get('median_ms', 0):.1f}ms")
    if m.topic == "plan":
        return f"A{a} plan: " + ", ".join(s["name"] for s in p.get("strategies", [])) + f" {p.get('flags')}"
    if m.topic == "candidate":
        return f"A{a} candidate diff:\n{p.get('diff', '')[:1200]}"
    if m.topic == "verdict":
        return f"A{a} verdict: {'ACCEPT' if p.get('accepted') else 'REJECT'} {p.get('reason')}"
    return f"{m.topic}: {json.dumps(p, default=str)[:300]}"


def _log_experience(state: RunState, plan: OptimizationPlan | None, verdict: Verdict) -> None:
    """Cross-run memory (Section 10.2): every judged LLM attempt becomes a
    labeled row the XGBoost dataset builder can learn from."""
    if plan is None or state.summary is None or state.variant in ("rule_only", "flags_only"):
        return
    if verdict.reason in ("plan_error", "toolerror", "missingcontext", "no_more_strategies"):
        return
    from optiflow.experiments.store import append_experience

    append_experience({
        "program_id": state.program_id, "run_id": state.run_id,
        "features": state.summary.features,
        "strategies": [s.name for s in plan.strategies],
        "accepted": verdict.accepted, "reason": verdict.reason, "speedup": verdict.speedup,
        "label_speedup": verdict.speedup if verdict.accepted else None,
    })
