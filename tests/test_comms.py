from optiflow.comms.blackboard import Blackboard
from optiflow.comms.broadcast import Broadcast
from optiflow.comms.p2p import PeerToPeer


def test_blackboard_publish_is_globally_readable():
    bb = Blackboard()
    bb.publish("analyzer", "summary", {"loops": 3})
    assert len(bb.read("anyone", "summary")) == 1
    assert len(bb.read("anyone")) == 1


def test_blackboard_send_is_still_readable_by_others():
    bb = Blackboard()
    bb.send("analyzer", "profiler", {"x": 1})
    assert len(bb.read("outsider")) == 1


def test_p2p_send_only_reaches_receiver():
    p2p = PeerToPeer()
    p2p.send("analyzer", "profiler", {"x": 1})
    assert len(p2p.read("profiler")) == 1
    assert len(p2p.read("strategist")) == 0


def test_p2p_has_no_shared_publish():
    import pytest

    p2p = PeerToPeer()
    with pytest.raises(NotImplementedError):
        p2p.publish("analyzer", "topic", {})


def test_broadcast_delivers_to_all_subscribers():
    bc = Broadcast(subscribers=["analyzer", "profiler", "strategist"])
    bc.publish("analyzer", "summary", {"loops": 3})
    assert len(bc.read("profiler")) == 1
    assert len(bc.read("strategist")) == 1
    assert len(bc.read("analyzer")) == 1


def test_broadcast_topic_filter():
    bc = Broadcast(subscribers=["a", "b"])
    bc.publish("a", "topic1", {"v": 1})
    bc.publish("a", "topic2", {"v": 2})
    assert len(bc.read("b", topic="topic1")) == 1


def test_stats_track_message_and_byte_counts():
    bb = Blackboard()
    bb.publish("analyzer", "summary", {"loops": 3})
    bb.publish("analyzer", "summary", {"loops": 4})
    stats = bb.stats()
    assert stats["messages"] == 2
    assert stats["bytes"] > 0
