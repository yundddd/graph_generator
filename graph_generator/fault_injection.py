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
    topic: str
    times: int


@dataclass
class DelayReceiveConfig:
    topic: str
    by: int


@dataclass
class DelayLoopConfig:
    delay: int
    times: int


@dataclass
class FaultInjectionConfig:
    # target node name
    inject_to: str
    # when to inject
    inject_at: int
    affect_publish: DropPublishConfig | MutatePublishConfig | None = None
    affect_receive: DropReceiveConfig | DelayReceiveConfig | None = None
    affect_loop: DelayLoopConfig | None = None
