"""Common interface every architecture implements.

Sequential, Hierarchical and Event-Driven all take the same agents and
channel and produce the same RunState shape, so swapping cfg.architecture
changes only who decides what runs next -- nothing about the agents,
tools or messaging changes underneath it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from optiflow.comms.base import Channel
from optiflow.core.schemas import RunState


@dataclass
class RunConfig:
    architecture: str
    messaging: str = "blackboard"
    prompt_style: str = "structured"
    model_assignment: str = "mixed"
    max_attempts: int = 5
    max_usd_per_run: float = 0.05
    bench_n: int = 10


class Architecture(ABC):
    def __init__(self, channel: Channel, cfg: RunConfig) -> None:
        self.channel = channel
        self.cfg = cfg

    @abstractmethod
    def run(self, program_id: str) -> RunState:
        ...
