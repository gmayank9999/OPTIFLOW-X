"""Common interface every architecture implements.

Sequential, Hierarchical and Event-Driven all drive the same Pipeline
steps (same agents, same tools, same channel) and produce the same
RunState shape, so swapping cfg.architecture changes only who decides
what runs next -- nothing about the agents, tools or messaging changes
underneath it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

from optiflow.comms.base import Channel
from optiflow.core.schemas import RunState

ARCHITECTURES = ("sequential", "hierarchical", "event")
VARIANTS = ("full", "no_rag", "no_xgb", "llm_only", "rule_only", "flags_only")
PROMPT_STYLES = ("structured", "react", "reflection")


@dataclass
class RunConfig:
    architecture: str = "sequential"
    messaging: str = "blackboard"
    prompt_style: str = "structured"
    model_assignment: str = "single-cloud"
    variant: str = "full"
    max_attempts: int = 5
    max_usd_per_run: float = 0.05
    bench_n: int | None = None  # None = adaptive, from the stability table
    experiment: str = "adhoc"
    run_id: str | None = None
    tags: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.architecture not in ARCHITECTURES:
            raise ValueError(f"architecture must be one of {ARCHITECTURES}")
        if self.variant not in VARIANTS:
            raise ValueError(f"variant must be one of {VARIANTS}")
        if self.prompt_style not in PROMPT_STYLES:
            raise ValueError(f"prompt_style must be one of {PROMPT_STYLES}")

    @property
    def uses_llm(self) -> bool:
        return self.variant not in ("rule_only", "flags_only")


EventSink = Callable[[dict], None]


class Architecture(ABC):
    name = "abstract"

    def __init__(self, channel: Channel, cfg: RunConfig, emit: EventSink | None = None, tools=None) -> None:
        self.channel = channel
        self.cfg = cfg
        self.emit = emit
        self._tools = tools  # injected ToolClient (tests); None = open an MCP session per run

    @abstractmethod
    def run(self, program_id: str) -> RunState:
        ...


def build(cfg: RunConfig, emit: EventSink | None = None, tools=None) -> Architecture:
    from optiflow.architectures.event_driven import EventDriven
    from optiflow.architectures.hierarchical import Hierarchical
    from optiflow.architectures.sequential import Sequential
    from optiflow.comms import make_channel

    arch = {"sequential": Sequential, "hierarchical": Hierarchical, "event": EventDriven}[cfg.architecture]
    return arch(make_channel(cfg.messaging), cfg, emit=emit, tools=tools)
