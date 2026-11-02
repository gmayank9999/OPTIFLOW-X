"""Tests for Prompt Styles (Structured, ReAct, Reflection, Few-Shot) and Personas.

Validates:
1. Prompt template composition and persona focus injection.
2. ReAct dynamic tools (knowledge_search and predict_strategies).
3. Reflection two-stage plan generation (draft -> critique -> revised plan).
4. Pipeline-level reflection event emission and draft plan persistence.
5. Strict validation of prompt styles and personas in RunConfig.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from optiflow.agents import strategist
from optiflow.agents.prompts import strategist as prompts
from optiflow.architectures.base import RunConfig
from optiflow.architectures.pipeline import Pipeline
from optiflow.comms import make_channel
from optiflow.core.schemas import OptimizationPlan, ProfileReport, ProgramSummary, TokenUsage


@pytest.fixture
def sample_summary() -> ProgramSummary:
    return ProgramSummary(
        program_id="matmul_naive",
        language="c",
        source="void matmul() { /* nested loops */ }",
        functions=["matmul"],
        loops=[{"function": "matmul", "depth": 3}],
        features={"max_loop_depth": 3.0, "stride_mismatch": 1.0, "has_recursion": 0.0},
        summary_text="Triple nested matrix multiplication",
    )


@pytest.fixture
def sample_profile() -> ProfileReport:
    return ProfileReport(
        baseline_runtime_ms=120.5,
        runtime_std_ms=2.1,
        peak_mem_kb=1024,
        ipc=1.2,
        l1_miss_rate=0.45,
        bottleneck_text="L1 cache miss hotspot in innermost loop",
    )


def test_personas_inject_distinct_focus_into_context(sample_summary, sample_profile):
    """Every persona should inject a specific role focus into the strategist prompt context."""
    for persona in prompts.PERSONAS:
        ctx = strategist.build_context(
            sample_summary,
            sample_profile,
            best_source=sample_summary.source,
            best_speedup=1.0,
            best_flags=["-O2"],
            persona=persona,
            use_rag=False,
            use_xgb=False,
        )
        assert ctx["_persona"] == persona
        focus = prompts.PERSONAS[persona]["focus"]
        if focus:
            assert focus in ctx["shared_context"]


def test_agent_creation_reflects_persona():
    """Agent title and backstory must match the specified persona."""
    agent_hpc = strategist.make_agent(persona="hpc_researcher")
    assert "HPC" in agent_hpc.role or "HPC" in getattr(agent_hpc, "backstory", "")

    agent_cautious = strategist.make_agent(persona="cautious_reviewer")
    assert "Correctness" in agent_cautious.role or "safety" in getattr(agent_cautious, "backstory", "").lower()


def test_few_shot_prompt_contains_worked_examples(sample_summary, sample_profile):
    """Few-shot prompt must embed the 3 worked examples before the rules."""
    ctx = strategist.build_context(
        sample_summary,
        sample_profile,
        best_source=sample_summary.source,
        best_speedup=1.0,
        best_flags=["-O2"],
        use_rag=False,
        use_xgb=False,
    )
    fmt = {k: v for k, v in ctx.items() if not k.startswith("_")}
    prompt = prompts.FEW_SHOT.format(**fmt)

    assert "WORKED EXAMPLES" in prompt
    assert "Example 1" in prompt
    assert "Example 2" in prompt
    assert "Example 3" in prompt
    assert "Rules:" in prompt


def test_react_tools_execute_and_record_calls(monkeypatch, sample_summary):
    """ReAct tools (knowledge_search and predict_strategies) must return strings and log calls."""
    monkeypatch.setattr("optiflow.agents.strategist.retrieve_text", lambda q, k=3: [f"Card for {q}"])

    info = {"tool_calls": []}
    tools = strategist._react_tools(sample_summary.features, info)
    assert len(tools) == 2

    k_tool, p_tool = tools[0], tools[1]
    assert k_tool.name == "knowledge_search"
    assert p_tool.name == "predict_strategies"

    # Execute predict_strategies
    p_result = p_tool.run()
    assert isinstance(p_result, str)
    assert any(c["tool"] == "predict_strategies" for c in info["tool_calls"])

    # Execute knowledge_search
    k_result = k_tool.run(query="loop interchange cache blocking")
    assert isinstance(k_result, str)
    assert "Card for loop interchange" in k_result
    assert any(c["tool"] == "knowledge_search" for c in info["tool_calls"])


def test_reflection_two_stage_execution_and_draft_capture(monkeypatch, sample_summary, sample_profile):
    """Reflection must call the model twice (draft and critique) and record both."""
    calls = []

    def mock_call(agent, prompt, expected, **kwargs):
        calls.append(prompt)
        usage = TokenUsage(prompt_tokens=100, completion_tokens=40, calls=1, cost_usd=0.0001)
        if len(calls) == 1:
            # First call: Draft plan
            draft = {
                "strategies": [{"name": "tiling", "target": "matmul", "rationale": "cache blocking", "confidence": 0.7}],
                "compiler": "gcc",
                "flags": ["-O3"],
            }
            return f"```json\n{json.dumps(draft)}\n```", usage
        else:
            # Second call: Revised plan after critique
            revised = {
                "strategies": [
                    {"name": "interchange", "target": "matmul", "rationale": "stride-1 accesses", "confidence": 0.85},
                    {"name": "tiling", "target": "matmul", "rationale": "cache blocking", "confidence": 0.80},
                ],
                "compiler": "gcc",
                "flags": ["-O3", "-march=native"],
            }
            return f"```json\n{json.dumps(revised)}\n```", usage

    monkeypatch.setattr("optiflow.core.llm.call", mock_call)

    ctx = strategist.build_context(
        sample_summary,
        sample_profile,
        best_source=sample_summary.source,
        best_speedup=1.0,
        best_flags=["-O2"],
        use_rag=False,
        use_xgb=False,
    )

    plan, usage, info = strategist.plan(None, ctx, attempt=1, prompt_style="reflection")

    # Verifications
    assert len(calls) == 2, "Reflection must invoke the model twice"
    assert "Critique it before it is executed" in calls[1]
    assert "draft" in info, "Initial draft must be captured in info"
    assert info["draft"]["strategies"][0]["name"] == "tiling"
    assert len(plan.strategies) == 2  # Revised plan has 2 strategies
    assert plan.strategies[0].name == "interchange"
    assert usage.calls == 2


def test_pipeline_records_reflection_draft_and_emits_event(monkeypatch, sample_summary, sample_profile):
    """Pipeline.plan must record draft_plan in rec['data'] and emit a reflection_draft event."""
    emitted = []

    def mock_call(agent, prompt, expected, **kwargs):
        usage = TokenUsage(prompt_tokens=50, completion_tokens=30, calls=1, cost_usd=0.0001)
        plan = {
            "strategies": [{"name": "interchange", "target": "matmul", "rationale": "test", "confidence": 0.8}],
            "compiler": "gcc",
            "flags": ["-O2"],
        }
        return json.dumps(plan), usage

    monkeypatch.setattr("optiflow.core.llm.call", mock_call)
    monkeypatch.setattr("optiflow.knowledge.retriever.retrieve", lambda s, p, k=4: [])

    cfg = RunConfig(
        architecture="sequential",
        messaging="blackboard",
        prompt_style="reflection",
        persona="compiler_engineer",
        variant="full",
    )
    channel = make_channel("blackboard")
    channel.post("analyzer", "summary", sample_summary.model_dump())
    channel.post("profiler", "profile", sample_profile.model_dump())

    pipeline = Pipeline(cfg, channel, tools=MagicMock(), program_id="matmul_naive", architecture="sequential", emit=emitted.append)
    pipeline.ensure_best_source()

    plan = pipeline.plan(attempt=1)
    assert isinstance(plan, OptimizationPlan)

    # Verify reflection event was emitted
    reflection_events = [e for e in emitted if e.get("type") == "reflection_draft"]
    assert len(reflection_events) == 1
    assert "draft" in reflection_events[0]
    assert reflection_events[0]["draft"]["strategies"][0]["name"] == "interchange"

    # Verify step_end recorded reflection data
    step_ends = [e for e in emitted if e.get("type") == "step_end" and e.get("agent") == "strategist"]
    assert len(step_ends) == 1
    rec_data = step_ends[0]["data"]
    assert rec_data["prompt_style"] == "reflection"
    assert rec_data["persona"] == "compiler_engineer"
    assert "draft_plan" in rec_data


def test_invalid_prompt_style_and_persona_are_rejected():
    """RunConfig must enforce valid prompt styles and personas."""
    with pytest.raises(ValueError, match="prompt_style must be one of"):
        RunConfig(prompt_style="magical_prompt")

    with pytest.raises(ValueError, match="persona must be one of"):
        RunConfig(persona="alien_hacker")
