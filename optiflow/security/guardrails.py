"""Guardrails for everything that reaches (or comes back from) an LLM.

Three surfaces:

1. **User text** -- the optional free-text guidance a user can attach to a
   run ("focus on cache behaviour"). Prompt-injection or abusive text is
   rejected outright (the API answers 422; nothing runs).
2. **Program source** -- the C code the agents read is untrusted data too:
   a comment like `/* ignore previous instructions and ... */` is a
   classic indirect prompt injection. Offending *comments* are replaced
   with a neutral marker before any LLM sees the source; comments don't
   affect semantics, so the program the sandbox compiles is unchanged.
3. **LLM output** -- plans, rewrites and feedback are scanned before they
   are used (abusive language, leaked instructions, injected directives).

Pattern-based by design: deterministic, fast, explainable in a report,
and testable. It is a first line of defence, not a proof of safety; the
sandbox, the flag whitelist, the source safety filter and the
rule-based Critic sit behind it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_INJECTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("override_instructions", re.compile(
        r"\b(ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}\b(previous|prior|above|earlier|all|any|your|the)\b"
        r"[^.\n]{0,20}\b(instructions?|prompts?|rules?|guidelines?|constraints?|directions?)\b", re.I)),
    ("role_hijack", re.compile(
        r"\b(you are now|from now on you are|act as|pretend (to be|you are)|roleplay as|new persona)\b", re.I)),
    ("system_prompt_probe", re.compile(
        r"\b(reveal|print|show|output|repeat|leak|tell me)\b[^.\n]{0,30}\b(system prompt|your (instructions|prompt|rules)|"
        r"hidden (prompt|instructions)|api[ _-]?keys?|secrets?|credentials?|\.env)\b", re.I)),
    ("chat_template_injection", re.compile(
        r"(<\|im_start\|>|<\|im_end\|>|<\|system\|>|\[/?INST\]|<<SYS>>|^\s*(###\s*)?(system|assistant)\s*:)", re.I | re.M)),
    ("jailbreak", re.compile(r"\b(jailbreak|DAN mode|developer mode enabled|do anything now|no restrictions)\b", re.I)),
    ("tool_abuse", re.compile(
        r"\b(curl|wget|nc|netcat)\s+(-\S+\s+)*https?://|rm\s+-rf\s+/|\bexfiltrat\w*|\bsend (it|this|them) to\b", re.I)),
    ("output_manipulation", re.compile(
        r"\b(always|must) (accept|approve|return)\b[^.\n]{0,30}\b(speedup|candidate|verdict|true)\b|"
        r"\bmark (this|it) as (accepted|correct|faster)\b", re.I)),
]

# Abusive language: a short, deliberately conservative list (insults,
# threats, slurs-adjacent profanity). Matched on word boundaries so
# identifiers like `skill` or `assert` don't trip it.
_ABUSE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("insult", re.compile(r"\b(idiot|moron|stupid|dumbass|imbecile|retard(ed)?|loser|worthless)\b", re.I)),
    ("profanity", re.compile(r"\b(fuck\w*|shit\w*|bitch\w*|bastard|asshole|cunt|dickhead)\b", re.I)),
    ("threat", re.compile(r"\b(i('ll| will) (kill|hurt|destroy) you|kill yourself|kys|die in a fire)\b", re.I)),
    ("hate", re.compile(r"\b(i hate (you|all)|go to hell)\b", re.I)),
]

_C_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)
NEUTRAL_COMMENT = "/* [comment removed by guardrail] */"


@dataclass
class Finding:
    kind: str          # "injection" | "abuse"
    rule: str          # e.g. "override_instructions"
    excerpt: str


@dataclass
class GuardrailResult:
    ok: bool
    surface: str
    findings: list[Finding] = field(default_factory=list)
    sanitized: str | None = None

    def summary(self) -> str:
        if self.ok:
            return f"{self.surface}: clean"
        rules = ", ".join(sorted({f"{f.kind}:{f.rule}" for f in self.findings}))
        return f"{self.surface}: {rules}"

    def as_dict(self) -> dict:
        return {"ok": self.ok, "surface": self.surface,
                "findings": [f.__dict__ for f in self.findings]}


class GuardrailViolation(ValueError):
    def __init__(self, result: GuardrailResult) -> None:
        super().__init__(f"guardrail blocked {result.summary()}")
        self.result = result


def scan(text: str, surface: str = "text", check_abuse: bool = True) -> GuardrailResult:
    findings: list[Finding] = []
    for rule, pattern in _INJECTION_PATTERNS:
        for m in pattern.finditer(text or ""):
            findings.append(Finding("injection", rule, _excerpt(text, m)))
    if check_abuse:
        for rule, pattern in _ABUSE_PATTERNS:
            for m in pattern.finditer(text or ""):
                findings.append(Finding("abuse", rule, _excerpt(text, m)))
    return GuardrailResult(ok=not findings, surface=surface, findings=findings)


def check_user_text(text: str | None, max_len: int = 600) -> GuardrailResult:
    """User-supplied guidance: length-limited, injection- and abuse-free."""
    text = (text or "").strip()
    result = scan(text, surface="user_instructions")
    if len(text) > max_len:
        result.ok = False
        result.findings.append(Finding("validation", "too_long", f"{len(text)} > {max_len} chars"))
    return result


def sanitize_source(source: str) -> GuardrailResult:
    """Neutralize comments that carry injection attempts. Code outside
    comments is left byte-identical (string literals that contain
    suspicious text are reported but kept: they may be program output)."""
    findings: list[Finding] = []

    def _replace(m: re.Match) -> str:
        comment = m.group(0)
        hit = scan(comment, check_abuse=False)
        if hit.ok:
            return comment
        findings.extend(hit.findings)
        # Keep line count stable so hotspot line numbers stay valid.
        return NEUTRAL_COMMENT + "\n" * comment.count("\n")

    sanitized = _C_COMMENT.sub(_replace, source)
    outside = scan(_C_COMMENT.sub(" ", source), check_abuse=False)
    for f in outside.findings:
        f.rule = f"{f.rule}(in code/string, kept)"
    findings.extend(outside.findings)
    return GuardrailResult(ok=not findings, surface="program_source", findings=findings, sanitized=sanitized)


def check_llm_output(text: str, surface: str) -> GuardrailResult:
    """Model output must not carry injected directives or abuse onward."""
    return scan(text, surface=surface)


def _excerpt(text: str, m: re.Match, pad: int = 30) -> str:
    start, end = max(0, m.start() - pad), min(len(text), m.end() + pad)
    return text[start:end].replace("\n", " ").strip()[:160]
