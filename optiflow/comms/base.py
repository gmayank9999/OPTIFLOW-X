"""Common interface for the three messaging mechanisms (Section 12.3).

Every implementation tracks its own message/byte counts so the messaging
experiment (E2) can compare token volume and message counts without
touching the architecture code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Message:
    sender: str
    topic: str
    payload: dict
    receiver: str | None = None


class Channel(ABC):
    def __init__(self) -> None:
        self._message_count = 0
        self._byte_count = 0

    @abstractmethod
    def publish(self, sender: str, topic: str, payload: dict) -> None:
        """Broadcast-style: visible to every reader of `topic`."""

    @abstractmethod
    def send(self, sender: str, receiver: str, payload: dict) -> None:
        """Peer-to-peer: visible only to `receiver`."""

    @abstractmethod
    def read(self, agent: str, topic: str | None = None) -> list[Message]:
        """What `agent` can currently see, optionally filtered by topic."""

    def stats(self) -> dict:
        return {"messages": self._message_count, "bytes": self._byte_count}

    def _record(self, payload: dict) -> None:
        self._message_count += 1
        self._byte_count += len(str(payload))
