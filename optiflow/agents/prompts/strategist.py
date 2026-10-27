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


# --- few-shot style ---------------------------------------------------------
# Three worked examples (profile -> plan), deliberately *not* the benchmark
# programs themselves, so the style teaches the reasoning pattern rather
# than leaking answers.
FEW_SHOT_EXAMPLES = """\
WORKED EXAMPLES (study the reasoning, then solve the real task):

Example 1
  Profile: 97% of samples in a triple loop over i, j, k; L1 miss rate 48%;
  stride_mismatch=1 (the innermost index walks the slow dimension of B).
  Plan: {{"strategies": [{{"name": "interchange", "target": "main:20-24",
    "params": {{"order": "i-k-j"}}, "rationale": "k innermost walks B by column;
    i-k-j makes both inner accesses unit-stride and cuts the 48% L1 miss rate",
    "confidence": 0.85}}], "compiler": "gcc", "flags": ["-O3", "-march=native"]}}

Example 2
  Profile: 100% of samples in a recursive function f(n) calling f(n-1) and
  f(n-2); IPC 4.1, negligible cache misses -- the work itself is exponential.
  Plan: {{"strategies": [{{"name": "memoize", "target": "f", "params": {{}},
    "rationale": "overlapping subproblems: caching results turns O(phi^n) into
    O(n); no flag can fix an exponential algorithm", "confidence": 0.9}}],
    "compiler": "gcc", "flags": ["-O2"]}}

Example 3
  Profile: 99% in two nested loops comparing a[j] with a[j+1] and swapping;
  integer data, output is a checksum of the sorted array.
  Plan: {{"strategies": [{{"name": "algorithmic", "target": "main", "params":
    {{"replace": "bubble sort -> qsort with a total-order comparator"}},
    "rationale": "O(n^2) -> O(n log n); the printed checksum only depends on
    the sorted order, so output stays identical", "confidence": 0.85}}],
    "compiler": "gcc", "flags": ["-O2"]}}

"""

FEW_SHOT = STRUCTURED.replace("Rules:", FEW_SHOT_EXAMPLES + "Rules:", 1)


# --- personas -----------------------------------------------------------------
# Same task and evidence, different role framing and priorities.
PERSONAS: dict[str, dict[str, str]] = {
    "default": {
        "title": "Optimization Strategist",
        "backstory": ("You are a performance engineer expert in GCC/LLVM, cache behaviour, loop "
                      "transformations and vectorization. You only propose changes that preserve "
                      "output, and you read profiles before guessing."),
        "focus": "",
    },
    "compiler_engineer": {
        "title": "Compiler Engineer",
        "backstory": ("You work on an optimizing compiler backend. You think in terms of what GCC "
                      "can and cannot prove: aliasing, loop-carried dependences, vectorization "
                      "legality, and which flags unlock which passes."),
        "focus": ("PERSONA FOCUS: prefer changes that let the compiler do the work (removing "
                  "aliasing and dependences, enabling vectorization, the right flags) before "
                  "hand-restructuring code."),
    },
    "hpc_researcher": {
        "title": "HPC Performance Researcher",
        "backstory": ("You optimize scientific codes on supercomputers. You think in terms of the "
                      "memory hierarchy, arithmetic intensity, cache blocking and data layout."),
        "focus": ("PERSONA FOCUS: reason from the memory hierarchy -- working-set size, reuse "
                  "distance, stride -- and aim for the largest asymptotic or locality win."),
    },
    "cautious_reviewer": {
        "title": "Correctness-First Reviewer",
        "backstory": ("You review performance patches for a safety-critical codebase. A wrong "
                      "answer is far worse than a slow one; you favour small, provably "
                      "output-preserving changes."),
        "focus": ("PERSONA FOCUS: propose the single safest change with a clear gain; avoid "
                  "anything that reorders floating-point arithmetic or depends on input sizes."),
    },
}

USER_GUIDANCE = "\nUSER GUIDANCE (from the person running this optimization; already screened): {instructions}\n"
