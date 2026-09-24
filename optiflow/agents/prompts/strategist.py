"""Prompt templates for the Optimization Strategist, keyed by prompting style
(Section 13.1: structured / ReAct / reflection)."""

STRUCTURED = """\
PROGRAM SUMMARY: {summary_json}
PROFILE: {profile_json}
ML PREDICTOR RANKING: {xgb_top5}
RETRIEVED KNOWLEDGE: {rag_chunks}
PREVIOUS ATTEMPTS: {history_compact}

Rules:
- Target the hotspot with the highest time share first.
- Do not repeat a strategy that already failed for the same reason.
- Prefer 1-2 strategies per attempt so the effect is attributable.
- Never use -ffast-math unless compare mode is float_tol.

Return ONLY JSON matching the OptimizationPlan schema:
{{"attempt": n, "strategies": [{{"name": "...", "target": "...", \
"params": {{}}, "rationale": "...", "confidence": 0.0}}], \
"compiler": "gcc", "flags": ["-O2"]}}
"""

REACT = """\
You are optimizing a C/C++ program. Work step by step.

PROGRAM SUMMARY: {summary_json}
PROFILE: {profile_json}
PREVIOUS ATTEMPTS: {history_compact}

You have tools: knowledge_search(query), predict_strategies(features_json).
Use the ReAct pattern:
Thought: what do you need to know before proposing a strategy?
Action: call a tool, or state "none needed"
Observation: the tool's result
... repeat until confident ...
Final Plan: OptimizationPlan JSON, same schema as the structured style.
"""

REFLECTION_DRAFT = """\
PROGRAM SUMMARY: {summary_json}
PROFILE: {profile_json}
ML PREDICTOR RANKING: {xgb_top5}
RETRIEVED KNOWLEDGE: {rag_chunks}
PREVIOUS ATTEMPTS: {history_compact}

Draft an OptimizationPlan (same JSON schema as the structured style).
"""

REFLECTION_CRITIQUE = """\
Your draft plan:
{draft_plan_json}

Self-critique before finalizing:
- What could break correctness (edge sizes, aliasing, overflow)?
- Is the effect attributable (not too many strategies at once)?
- Does it repeat something that already failed?

Return the revised OptimizationPlan JSON, same schema.
"""
