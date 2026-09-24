"""Blackboard: one shared store, every agent reads and writes the fields
it needs. Highest context volume of the three (everything is visible to
everyone), fewest missing-context errors.
"""

from __future__ import annotations

from optiflow.comms.base import Channel, Message


class Blackboard(Channel):
    def __init__(self) -> None:
        super().__init__()
        self._store: dict[str, list[Message]] = {}

    def publish(self, sender: str, topic: str, payload: dict) -> None:
        self._record(payload)
        self._store.setdefault(topic, []).append(Message(sender, topic, payload))

    def send(self, sender: str, receiver: str, payload: dict) -> None:
        # On a blackboard, a direct send is just a publish to a
        # receiver-scoped topic: still globally readable, unlike true P2P.
        self.publish(sender, f"to:{receiver}", payload)

    def read(self, agent: str, topic: str | None = None) -> list[Message]:
        if topic is not None:
            return list(self._store.get(topic, []))
        all_messages: list[Message] = []
        for messages in self._store.values():
            all_messages.extend(messages)
        return all_messages
