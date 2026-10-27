"""Blackboard: one shared store, every agent reads and writes the fields
it needs. Highest context volume of the three (everything is visible to
everyone), fewest missing-context errors.
"""

from __future__ import annotations

from optiflow.comms.base import Channel, Message


class Blackboard(Channel):
    name = "blackboard"

    def __init__(self) -> None:
        super().__init__()
        self._store: dict[str, list[Message]] = {}

    def publish(self, sender: str, topic: str, payload: dict) -> None:
        with self._lock:
            seq = self._record(payload)
            self._store.setdefault(topic, []).append(Message(sender, topic, payload, seq=seq))

    def send(self, sender: str, receiver: str, payload: dict, topic: str = "direct") -> None:
        # On a blackboard, a direct send is just a publish to a
        # receiver-scoped topic: still globally readable, unlike true P2P.
        self.publish(sender, f"to:{receiver}", payload)

    def read(self, agent: str, topic: str | None = None) -> list[Message]:
        with self._lock:
            self._count_read()
            if topic is not None:
                return list(self._store.get(topic, []))
            all_messages = [m for messages in self._store.values() for m in messages]
            return sorted(all_messages, key=lambda m: m.seq)
