"""Builds a CrewAI LLM instance for a given agent role."""

from __future__ import annotations

from crewai import LLM

from optiflow.core.config import model_for


def llm_for(role: str, temperature: float = 0.2, assignment: str | None = None) -> LLM:
    return LLM(model=model_for(role, assignment), temperature=temperature)
