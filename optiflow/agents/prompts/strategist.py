"""Prompt templates for the Optimization Strategist, keyed by prompting style
(Section 13.1: structured / ReAct / reflection)."""

STRATEGY_MENU = """\
Allowed strategy names (use exactly these): flags, interchange, tiling, vectorize,
unroll, fusion, fission, soa, hoist, memoize, algorithmic.
- flags: compiler flags only (put them in "flags").
- algorithmic: replace an asymptotically worse algorithm with a better one that
  produces byte-identical output (e.g. memoized DP, sort once instead of per query).
Allowed flags: -O1 -O2 -O3 -march=native -mtune=native -funroll-loops -fopenmp-simd
-flto -fno-math-errno -ftree-vectorize -fomit-frame-pointer{unsafe_flags}."""

PLAN_SCHEMA = """\
Return ONLY one JSON object, no prose, matching:
{{"strategies": [{{"name": "<strategy>", "target": "<function or line range>",
  "params": {{}}, "rationale": "<one sentence citing the profile>", "confidence": 0.0-1.0}}],
 "compiler": "gcc" | "clang", "flags": ["-O2", ...]}}"""

CONTEXT = """\
PROGRAM: {program_id} ({lang}), output compared {compare_mode}.
CURRENT BEST: {best_speedup:.2f}x over the -O2 baseline, built with flags {best_flags}.
CURRENT BEST SOURCE (line-numbered):
{source}

STRUCTURE: {summary_text}
STATIC FEATURES: {features_json}
PROFILE: {profile_json}
"""

STRUCTURED = CONTEXT + """\
ML PREDICTOR RANKING (P(strategy gives >=1.10x), small-data prior, not ground truth): {xgb_ranked}
RETRIEVED KNOWLEDGE:
{rag_chunks}

PREVIOUS ATTEMPTS:
{history_compact}
{shared_context}
Rules:
- Target the hotspot with the highest time share first.
- Do not repeat a strategy that already failed for the same reason.
- Build on the current best: it already contains every accepted change.
- Prefer 1-2 strategies per attempt so the effect is attributable.
- Output must stay byte-identical (or within tolerance for float_tol).
""" + STRATEGY_MENU + "\n\n" + PLAN_SCHEMA

REACT = CONTEXT + """\
PREVIOUS ATTEMPTS:
{history_compact}
{shared_context}
You have two tools:
- knowledge_search(query): technique cards from the optimization knowledge base.
- predict_strategies(): the ML predictor's ranking for this program.
Work in the ReAct pattern: Thought -> Action (call a tool when you need evidence)
-> Observation -> ... until confident, then give the final plan.
""" + STRATEGY_MENU + "\n\nFinal answer: " + PLAN_SCHEMA

REFLECTION_DRAFT = STRUCTURED.replace(
    "Return ONLY one JSON object", "Draft a plan. Return ONLY one JSON object"
)

REFLECTION_CRITIQUE = """\
You drafted this optimization plan for {program_id}:
{draft_plan_json}

PROFILE: {profile_json}
PREVIOUS ATTEMPTS:
{history_compact}

Critique it before it is executed:
- Could it break correctness (edge sizes like n=1 or n=33, aliasing, overflow,
  float reassociation under exact compare)?
- Does it target where the time actually goes (the hotspot lines)?
- Is the effect attributable (not too many strategies at once)?
- Does it repeat something that already failed?
Then return the REVISED plan. """ + PLAN_SCHEMA

RETRY_SUFFIX = """

Your previous answer could not be used: {error}
Answer again with ONLY the JSON object."""
