from optiflow.comms.base import Channel


def make_channel(name: str) -> Channel:
    from optiflow.comms.blackboard import Blackboard
    from optiflow.comms.broadcast import Broadcast
    from optiflow.comms.p2p import PeerToPeer

    channels = {"blackboard": Blackboard, "p2p": PeerToPeer, "broadcast": Broadcast}
    if name not in channels:
        raise ValueError(f"unknown messaging mode {name!r}; expected one of {sorted(channels)}")
    return channels[name]()
