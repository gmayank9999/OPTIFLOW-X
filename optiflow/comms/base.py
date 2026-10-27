"""Common interface for the three messaging mechanisms (Section 12.3).

Agents exchange *all* pipeline data through a channel: each step posts its
output under a topic, and each step reads its inputs back from what the
channel lets that agent see. The mechanisms differ in visibility:

- Blackboard: one shared store; every agent can read every topic.
- Peer-to-peer: a message reaches only the receivers in ROUTES.
- Broadcast: every message is delivered into every agent's inbox.

That difference is what experiment E2 measures: what each agent can see
changes how much context the Strategist gets (and pays tokens for), and
whether something it needed got lost. Every channel counts messages,
deliveries, bytes and reads.
"""

from __future__ import annotations

import json
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

AGENTS = ("analyzer", "profiler", "strategist", "transformer", "compiler_exec", "benchmark", "critic", "manager")

# Who needs which topic. Peer-to-peer delivers only along these edges;
# blackboard and broadcast ignore them (everything is visible).
ROUTES: dict[str, tuple[str, ...]] = {
    "summary": ("profiler", "strategist", "transformer", "compiler_exec", "manager"),
    "profile": ("strategist", "manager"),
    "plan": ("transformer", "manager"),
    "candidate": ("compiler_exec",),
    "build": ("benchmark", "critic"),
    "tests": ("benchmark", "critic"),
    "compare": ("critic",),
    "verdict": ("strategist", "transformer", "manager"),
}


@dataclass
class Message:
    sender: str
    topic: str
    payload: dict
    receiver: str | None = None
    seq: int = 0
    meta: dict = field(default_factory=dict)


class Channel(ABC):
    name = "abstract"

    def __init__(self) -> None:
        self._message_count = 0
        self._delivery_count = 0
        self._byte_count = 0
        self._read_count = 0
        self._seq = 0
        self._lock = threading.RLock()

    @abstractmethod
    def publish(self, sender: str, topic: str, payload: dict) -> None:
        """Broadcast-style: visible to every reader of `topic`."""

    @abstractmethod
    def send(self, sender: str, receiver: str, payload: dict, topic: str = "direct") -> None:
        """Peer-to-peer: visible only to `receiver`."""

    @abstractmethod
    def read(self, agent: str, topic: str | None = None) -> list[Message]:
        """What `agent` can currently see, optionally filtered by topic."""

    def post(self, sender: str, topic: str, payload: dict) -> None:
        """How a pipeline step hands its output on. Mechanism-specific
        delivery is decided by publish/send in each subclass."""
        self.publish(sender, topic, payload)

    def latest(self, agent: str, topic: str) -> dict | None:
        messages = self.read(agent, topic)
        return messages[-1].payload if messages else None

    def stats(self) -> dict:
        return {
            "mechanism": self.name,
            "messages": self._message_count,
            "deliveries": self._delivery_count,
            "bytes": self._byte_count,
            "reads": self._read_count,
        }

    def _record(self, payload: dict, deliveries: int = 1) -> int:
        self._message_count += 1
        self._delivery_count += deliveries
        self._byte_count += len(json.dumps(payload, default=str))
        self._seq += 1
        return self._seq

    def _count_read(self) -> None:
        self._read_count += 1
