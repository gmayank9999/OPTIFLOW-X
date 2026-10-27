"""Peer-to-peer: a sender writes directly into the receiver's inbox.
Lowest volume, but an agent that isn't explicitly addressed sees
nothing -- the risk this mode is measured on is "lost context".

`post()` delivers along the static routing table in comms.base.ROUTES;
there are no shared topics, so `publish()` is not supported.
"""

from __future__ import annotations

from collections import defaultdict

from optiflow.comms.base import ROUTES, Channel, Message


class PeerToPeer(Channel):
    name = "p2p"

    def __init__(self, routes: dict[str, tuple[str, ...]] | None = None) -> None:
        super().__init__()
        self._routes = routes if routes is not None else ROUTES
        self._inboxes: dict[str, list[Message]] = defaultdict(list)

    def publish(self, sender: str, topic: str, payload: dict) -> None:
        raise NotImplementedError("PeerToPeer has no shared topics; use send() or post()")

    def send(self, sender: str, receiver: str, payload: dict, topic: str = "direct") -> None:
        with self._lock:
            seq = self._record(payload)
            self._inboxes[receiver].append(Message(sender, topic, payload, receiver, seq=seq))

    def post(self, sender: str, topic: str, payload: dict) -> None:
        for receiver in self._routes.get(topic, ()):
            if receiver != sender:
                self.send(sender, receiver, payload, topic=topic)

    def read(self, agent: str, topic: str | None = None) -> list[Message]:
        with self._lock:
            self._count_read()
            messages = self._inboxes.get(agent, [])
            if topic is None:
                return list(messages)
            return [m for m in messages if m.topic == topic]
