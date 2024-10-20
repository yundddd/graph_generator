from dataclasses import dataclass


@dataclass
class DropPublishConfig:
    topic: str
    times: int


@dataclass
class MutatePublishConfig:
    topic: str
    value: int


@dataclass
class DropReceiveConfig:
    """
    This config describes which topic to drop received messages from and how many times.
    """

    topic: str
    times: int


@dataclass
class DelayReceiveConfig:
    """
    This config describes which topic to delay a received message.
    It only delays a single instance.
    """

    topic: str
    delay: int


@dataclass
class DelayLoopConfig:
    """
    This config describes how long to delay a loop work. Subsequent loop work will also contain the same phase shift.
     For example if a node nominally execute periodic work as:
      t0        t1        t2        t3
       |_________|_________|_________|
    Delaying work at t1 translates to:
      t0              t1        t2        t3
       |_______________|_________|_________|
    A single config can only delay work once
    """

    delay: int


@dataclass
class DropLoopConfig:
    """
    This config describes the number of times to drop periodic work.
    We will still schedule subsequent periodic work with the same phase.
    For example if a node nominally execute periodic work as:
      t0        t1        t2        t3
       |_________|_________|_________|
    Dropping two periodic work at t1 translates to:
      t0                             t3
       |_____________________________|
    A single config can only delay work once
    """

    times: int


@dataclass
class FaultInjectionConfig:
    # target node name
    inject_to: str
    # when to inject
    inject_at: int
    affect_publish: DropPublishConfig | MutatePublishConfig | None = None
    affect_receive: DropReceiveConfig | DelayReceiveConfig | None = None
    affect_loop: DelayLoopConfig | DropLoopConfig | None = None
