from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class PublishConfig:
    """
    PublishConfig defines that a node will publish to a topic with a value defined by
    value_range. The delay_range models any transmission delay (unit-less)
    """

    topic: str
    value_range: Tuple[int, int]
    delay_range: Tuple[int, int] = (0, 0)


@dataclass
class CallbackConfig:
    """
    A CallbackConfig defines what to do when a node performs a work.
    """

    publish: List[PublishConfig] | None = None


@dataclass
class SubscriptionConfig:
    """
    A SubscriptionConfig defines what a node does when it receives a message from a topic.
    If the received message is within the valid_range, it will execute a nominal_callback.
    Otherwise, it will execute faulted_callback. This is useful to simulate handling bad
    inputs from upstream.
    A watchdog is a mechanism for nodes to report faults when it hasn't heard from this
    topic for watchdog time units since last receive.
    If the message is not received within watchdog time, the watchdog_callback wil be
    executed. This is useful to simulate handling dropped or delayed messages from upstream.
    """

    topic: str
    valid_range: Tuple[int, int]
    watchdog: int

    nominal_callback: CallbackConfig
    faulted_callback: CallbackConfig
    watchdog_callback: CallbackConfig


@dataclass
class LoopConfig:
    period: int
    callback: CallbackConfig


@dataclass
class NodeConfig:
    name: str
    loop: LoopConfig | None = None
    subscribe: List[SubscriptionConfig] | None = None


class Node:
    def __init__(self, config: NodeConfig):
        self.config = config
        Node._validate_config(config)

    @staticmethod
    def _validate_config(config):
        if not config.name or len(config.name) == 0:
            raise ValueError("Name must be provided for a node")
        if not config.loop and not config.subscribe:
            raise ValueError("A node must have at least one loop or subscription")
        if config.subscribe and len(config.subscribe) == 0:
            raise ValueError("Subscribe config cannot be an empty list")

    def __str__(self):
        return f"Node: {self.config.name}"

    def __repr__(self):
        return self.__str__()
