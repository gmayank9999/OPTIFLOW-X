"""Broadcast: every publish is delivered to every registered agent's
inbox, regardless of whether they need it. Most deliveries of the three
modes; measures the cost of agents processing irrelevant traffic.
"""

from __future__ import annotations

from collections import defaultdict

from optiflow.comms.base import AGENTS, Channel, Message


class Broadcast(Channel):
    name = "broadcast"

    def __init__(self, subscribers: list[str] | None = None) -> None:
        super().__init__()
        self._subscribers: list[str] = list(subscribers if subscribers is not None else AGENTS)
        self._inboxes: dict[str, list[Message]] = defaultdict(list)

    def register(self, agent: str) -> None:
        with self._lock:
            if agent not in self._subscribers:
                self._subscribers.append(agent)

    def publish(self, sender: str, topic: str, payload: dict) -> None:
        with self._lock:
            seq = self._record(payload, deliveries=len(self._subscribers))
            message = Message(sender, topic, payload, seq=seq)
            for agent in self._subscribers:
                self._inboxes[agent].append(message)

    def send(self, sender: str, receiver: str, payload: dict, topic: str = "direct") -> None:
        # Broadcast has no private channel: a "send" still goes to everyone.
        self.publish(sender, f"to:{receiver}", payload)

    def read(self, agent: str, topic: str | None = None) -> list[Message]:
        with self._lock:
            self._count_read()
            messages = self._inboxes.get(agent, [])
            if topic is None:
                return list(messages)
            return [m for m in messages if m.topic == topic]
