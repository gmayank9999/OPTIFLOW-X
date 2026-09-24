"""Broadcast: every publish is delivered to every registered agent's
inbox, regardless of whether they need it. Most messages of the three
modes; measures the cost of agents processing irrelevant traffic.
"""

from __future__ import annotations

from collections import defaultdict

from optiflow.comms.base import Channel, Message


class Broadcast(Channel):
    def __init__(self, subscribers: list[str] | None = None) -> None:
        super().__init__()
        self._subscribers: list[str] = list(subscribers or [])
        self._inboxes: dict[str, list[Message]] = defaultdict(list)

    def register(self, agent: str) -> None:
        if agent not in self._subscribers:
            self._subscribers.append(agent)

    def publish(self, sender: str, topic: str, payload: dict) -> None:
        self._record(payload)
        message = Message(sender, topic, payload)
        for agent in self._subscribers:
            self._inboxes[agent].append(message)

    def send(self, sender: str, receiver: str, payload: dict) -> None:
        # Broadcast has no private channel: a "send" still goes to everyone.
        self.publish(sender, f"to:{receiver}", payload)

    def read(self, agent: str, topic: str | None = None) -> list[Message]:
        messages = self._inboxes.get(agent, [])
        if topic is None:
            return list(messages)
        return [m for m in messages if m.topic == topic]
