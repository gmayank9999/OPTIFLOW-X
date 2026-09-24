"""Peer-to-peer: a sender writes directly into the receiver's inbox.
Lowest token volume, but an agent that isn't explicitly addressed sees
nothing -- the risk this mode is measured on is "lost context".
"""

from __future__ import annotations

from collections import defaultdict

from optiflow.comms.base import Channel, Message


class PeerToPeer(Channel):
    def __init__(self) -> None:
        super().__init__()
        self._inboxes: dict[str, list[Message]] = defaultdict(list)

    def publish(self, sender: str, topic: str, payload: dict) -> None:
        raise NotImplementedError("PeerToPeer has no shared topics; use send()")

    def send(self, sender: str, receiver: str, payload: dict) -> None:
        self._record(payload)
        self._inboxes[receiver].append(Message(sender, "direct", payload, receiver))

    def read(self, agent: str, topic: str | None = None) -> list[Message]:
        return list(self._inboxes.get(agent, []))
