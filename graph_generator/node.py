from collections import defaultdict
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, List, Tuple

from graph_generator.fault_injection import (
    DelayLoopConfig,
    DelayReceiveConfig,
    DropLoopConfig,
    DropReceiveConfig,
    FaultInjectionConfig,
)


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


class NominalCallbackConfig(CallbackConfig):
    pass


class InvalidInputCallbackConfig(CallbackConfig):
    pass


class LostInputCallbackConfig(CallbackConfig):
    pass


class LoopCallbackConfig(CallbackConfig):
    pass


@dataclass
class SubscriptionConfig:
    """
    A SubscriptionConfig defines what a node does when it receives a message from a topic.
    If the received message is within the valid_range, it will execute a nominal_callback.
    Otherwise, it will execute invalid_input_callback. This is useful to simulate handling bad
    inputs from upstream.
    A watchdog is a mechanism for nodes to report faults when it hasn't heard from this
    topic for watchdog time units since last receive.
    If the message is not received within watchdog time, the lost_input_callback wil be
    executed. This is useful to simulate handling dropped or delayed messages from upstream.
    """

    topic: str
    valid_range: Tuple[int, int]
    watchdog: int

    nominal_callback: NominalCallbackConfig
    invalid_input_callback: InvalidInputCallbackConfig
    lost_input_callback: LostInputCallbackConfig


@dataclass
class LoopConfig:
    period: int
    callback: CallbackConfig


@dataclass
class NodeConfig:
    name: str
    loop: LoopConfig | None = None
    subscribe: List[SubscriptionConfig] | None = None


class NodeFeatureTemplate:
    class FeatureIndex(Enum):
        NODE_NAME_FEATURE_INDEX = 0
        EVENT_TIMESTAMP_FEATURE_INDEX = 1
        EVENT_TYPE_FEATURE_INDEX = 2
        CALLBACK_FEATURE_INDEX = 3

    EVENT_FEATURE_MAPPING = {
        LoopConfig: 2,
        SubscriptionConfig: 3,
    }
    CALLBACK_FEATURE_MAPPING = {
        NominalCallbackConfig: 2,
        InvalidInputCallbackConfig: 3,
        LostInputCallbackConfig: 4,
        LoopCallbackConfig: 5,
    }

    def initial_feature(self, config: NodeConfig):
        feature: List[Any] = [1] * len(NodeFeatureTemplate.FeatureIndex)
        feature[NodeFeatureTemplate.FeatureIndex.NODE_NAME_FEATURE_INDEX.value] = (
            config.name
        )
        return feature

    def update_event_feature(
        self, feature: List, event: LoopConfig | SubscriptionConfig, timestamp: int
    ):
        feature[NodeFeatureTemplate.FeatureIndex.EVENT_TYPE_FEATURE_INDEX.value] = (
            NodeFeatureTemplate.EVENT_FEATURE_MAPPING[type(event)]
        )
        feature[
            NodeFeatureTemplate.FeatureIndex.EVENT_TIMESTAMP_FEATURE_INDEX.value
        ] = timestamp

    def update_callback_feature(
        self,
        feature: List,
        callback: (
            NominalCallbackConfig
            | InvalidInputCallbackConfig
            | LostInputCallbackConfig
            | LoopCallbackConfig
        ),
    ):
        feature[NodeFeatureTemplate.FeatureIndex.CALLBACK_FEATURE_INDEX.value] = (
            NodeFeatureTemplate.CALLBACK_FEATURE_MAPPING[type(callback)]
        )


class Node:
    def __init__(self, config: NodeConfig):
        self.config = config
        self.feature_template = NodeFeatureTemplate()
        self.feature = self.feature_template.initial_feature(self.config)
        Node._validate_config(config)
        self.init_fault_injection_state()

    def update_event_feature(self, **kwarg):
        self.feature_template.update_event_feature(self.feature, **kwarg)

    def update_callback_feature(self, **kwarg):
        self.feature_template.update_callback_feature(self.feature, **kwarg)

    def init_fault_injection_state(self):
        self.fault_injection_config: FaultInjectionConfig | None = None
        self.dropped_loop_count = 0
        self.delayed_loop_count = 0
        self.dropped_receive_count = defaultdict(int)

    def drop_loop(self, cur_time: int):
        print(f"    \033[91mNode: {self.config.name} dropped loop at {cur_time}\033[0m")
        self.dropped_loop_count += 1

    def delay_loop(self, next_time: int):
        print(
            "    \033[91mNode: "
            f"{self.config.name} delayed loop to {next_time}\033[0m"
        )
        # Since we can only delay once, erase the config to avoid accounting.
        self.fault_injection_config = None
        pass

    def drop_receive(self, topic: str):
        print(
            "    \033[91mNode: "
            f"{self.config.name} dropped received message from topic "
            f"{topic}\033[0m"
        )
        self.dropped_receive_count[topic] += 1

    def delay_receive(self, topic: str):
        print(
            "    \033[91mNode: "
            f"{self.config.name} delayed received message from topic "
            f"{topic}\033[0m"
        )
        # Since we can only delay once, erase the config to avoid accounting.
        self.fault_injection_config = None
        pass

    def should_drop_loop(self, cur_time: int):
        return (
            self.fault_injection_config
            and self.fault_injection_config.affect_loop
            and isinstance(self.fault_injection_config.affect_loop, DropLoopConfig)
            and cur_time >= self.fault_injection_config.inject_at
            and self.dropped_loop_count < self.fault_injection_config.affect_loop.times
        )

    def should_delay_loop(self, cur_time: int):
        return (
            self.fault_injection_config
            and self.fault_injection_config.affect_loop
            and isinstance(self.fault_injection_config.affect_loop, DelayLoopConfig)
            and cur_time >= self.fault_injection_config.inject_at
        )

    def should_drop_receive(self, cur_time: int, topic: str):
        return (
            self.fault_injection_config
            and self.fault_injection_config.affect_receive
            and isinstance(
                self.fault_injection_config.affect_receive, DropReceiveConfig
            )
            and cur_time >= self.fault_injection_config.inject_at
            and self.dropped_receive_count[topic]
            < self.fault_injection_config.affect_receive.times
        )

    def should_delay_receive(self, cur_time: int, topic: str):
        return (
            self.fault_injection_config
            and self.fault_injection_config.affect_receive
            and isinstance(
                self.fault_injection_config.affect_receive, DelayReceiveConfig
            )
            and cur_time >= self.fault_injection_config.inject_at
        )

    @staticmethod
    def _validate_config(config):
        if not config.name or len(config.name) == 0:
            raise ValueError("Name must be provided for a node")
        if not config.loop and not config.subscribe:
            raise ValueError("A node must have at least one loop or subscription")
        if config.subscribe and len(config.subscribe) == 0:
            raise ValueError("Subscribe config cannot be an empty list")

    def __gt__(self, other):
        return self.config.name > other.config.name

    def __str__(self):
        return f"Node: {self.config.name}"
