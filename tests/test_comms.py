import pytest

from optiflow.comms import make_channel
from optiflow.comms.base import ROUTES
from optiflow.comms.blackboard import Blackboard
from optiflow.comms.broadcast import Broadcast
from optiflow.comms.p2p import PeerToPeer


def test_blackboard_publish_is_globally_readable():
    bb = Blackboard()
    bb.publish("analyzer", "summary", {"x": 1})
    assert bb.read("strategist", "summary")[0].payload == {"x": 1}
    assert bb.read("critic", "summary")[0].payload == {"x": 1}


def test_blackboard_send_is_still_readable_by_others():
    bb = Blackboard()
    bb.send("critic", "strategist", {"feedback": "try tiling"})
    assert bb.read("transformer", "to:strategist")[0].payload == {"feedback": "try tiling"}


def test_blackboard_read_all_is_in_publish_order():
    bb = Blackboard()
    bb.publish("a", "t1", {"n": 1})
    bb.publish("a", "t2", {"n": 2})
    bb.publish("a", "t1", {"n": 3})
    assert [m.payload["n"] for m in bb.read("x")] == [1, 2, 3]


def test_p2p_send_only_reaches_receiver():
    p2p = PeerToPeer()
    p2p.send("critic", "strategist", {"feedback": "x"})
    assert len(p2p.read("strategist")) == 1
    assert p2p.read("transformer") == []


def test_p2p_has_no_shared_publish():
    with pytest.raises(NotImplementedError):
        PeerToPeer().publish("a", "t", {})


def test_p2p_post_follows_the_routing_table():
    p2p = PeerToPeer()
    p2p.post("profiler", "profile", {"ipc": 1.2})
    for agent in ROUTES["profile"]:
        assert p2p.latest(agent, "profile") == {"ipc": 1.2}
    assert p2p.latest("transformer", "profile") is None
    assert p2p.stats()["messages"] == len(ROUTES["profile"])


def test_post_works_on_every_mechanism():
    # Sequential.run posts on whatever channel it's given; P2P used to crash here.
    for name in ("blackboard", "p2p", "broadcast"):
        ch = make_channel(name)
        ch.post("analyzer", "summary", {"ok": True})
        assert ch.latest("strategist", "summary") == {"ok": True}


def test_broadcast_delivers_to_all_subscribers():
    bc = Broadcast(subscribers=["a", "b", "c"])
    bc.publish("a", "news", {"v": 1})
    for agent in ("a", "b", "c"):
        assert len(bc.read(agent)) == 1
    assert bc.stats()["deliveries"] == 3


def test_broadcast_topic_filter():
    bc = Broadcast(subscribers=["a"])
    bc.publish("x", "t1", {})
    bc.publish("x", "t2", {})
    assert len(bc.read("a", "t1")) == 1


def test_stats_track_message_and_byte_counts():
    bb = Blackboard()
    bb.publish("a", "t", {"k": "v"})
    bb.read("b")
    stats = bb.stats()
    assert stats["messages"] == 1 and stats["bytes"] > 0 and stats["reads"] == 1


def test_unknown_mechanism_is_rejected():
    with pytest.raises(ValueError):
        make_channel("carrier_pigeon")
