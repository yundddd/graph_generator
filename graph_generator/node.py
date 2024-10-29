from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, List, Tuple

from pydantic import BaseModel

from graph_generator.fault_injection import (
    DelayLoopConfig,
    DelayReceiveConfig,
    DropLoopConfig,
    DropReceiveConfig,
    FaultInjectionConfig,
)


class PublishConfig(BaseModel):
    """
    PublishConfig defines that a node will publish to a topic with a value defined by
    value_range. The delay_range models any transmission delay (unit-less)
    """

    topic: str
    value_range: Tuple[int, int]
    delay_range: Tuple[int, int] = (0, 0)


class CallbackConfig(BaseModel):
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


class SubscriptionConfig(BaseModel):
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
    watchdog: int | None = None

    nominal_callback: NominalCallbackConfig | None = None
    invalid_input_callback: InvalidInputCallbackConfig | None = None
    lost_input_callback: LostInputCallbackConfig | None = None


class LoopConfig(BaseModel):
    period: int
    callback: CallbackConfig


class NodeConfig(BaseModel):
    name: str
    loop: LoopConfig | None = None
    subscribe: List[SubscriptionConfig] | None = None

    @staticmethod
    def num_publications(config: NodeConfig) -> int:
        """
        Calculates the total number of publications for a given node configuration.

        This method counts the number of topics a node will publish to, based on its loop
        callback and subscription callbacks. It adds up the number of topics published by
        the loop callback, and for each subscription, it includes publications from the
        nominal, invalid input, and lost input callbacks.

        Args:
            config (NodeConfig): The configuration of the node, including its loop and subscriptions.

        Returns:
            int: The total number of publications for the node.
        """
        ret = 0
        if config.loop:
            ret = len(config.loop.callback.publish)
        if config.subscribe:
            for sub in config.subscribe:
                if sub.nominal_callback:
                    ret += len(sub.nominal_callback.publish)
                if sub.invalid_input_callback:
                    ret += len(sub.invalid_input_callback.publish)
                if sub.lost_input_callback:
                    ret += len(sub.lost_input_callback.publish)
        return ret


class NodeFeatureTemplate:
    class FeatureIndex(Enum):
        # static features (constant based on node config):
        NODE_NAME = 0
        NUM_SUBSCRIPTIONS = auto()
        NUM_PUBLICATIONS = auto()
        LOOP_PERIOD = auto()

        # dynamic features (changes at runtime)
        LAST_EVENT_TIMESTAMP = auto()
        LAST_EVENT_TYPE = auto()
        CALLBACK_TYPE = auto()
        LOOP_COUNT = auto()
        SUBSCRIPTION_TOTAL_COUNT = auto()
        PUBLISH_COUNT = auto()

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
        feature[NodeFeatureTemplate.FeatureIndex.NODE_NAME.value] = config.name
        feature[NodeFeatureTemplate.FeatureIndex.LOOP_PERIOD.value] = (
            config.loop.period if config.loop else 0
        )
        feature[NodeFeatureTemplate.FeatureIndex.NUM_SUBSCRIPTIONS.value] = (
            len(config.subscribe) if config.subscribe else 0
        )
        feature[NodeFeatureTemplate.FeatureIndex.NUM_PUBLICATIONS.value] = (
            NodeConfig.num_publications(config)
        )
        return feature

    def update_event_feature(
        self, feature: List, event: LoopConfig | SubscriptionConfig, timestamp: int
    ):
        feature[NodeFeatureTemplate.FeatureIndex.LAST_EVENT_TYPE.value] = (
            NodeFeatureTemplate.EVENT_FEATURE_MAPPING[type(event)]
        )
        feature[NodeFeatureTemplate.FeatureIndex.LAST_EVENT_TIMESTAMP.value] = timestamp
        if isinstance(event, LoopConfig):
            feature[NodeFeatureTemplate.FeatureIndex.LOOP_COUNT.value] += 1
        else:
            feature[
                NodeFeatureTemplate.FeatureIndex.SUBSCRIPTION_TOTAL_COUNT.value
            ] += 1

    def update_publish_feature(self, feature: List):
        feature[NodeFeatureTemplate.FeatureIndex.PUBLISH_COUNT.value] += 1

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
        feature[NodeFeatureTemplate.FeatureIndex.CALLBACK_TYPE.value] = (
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

    def update_publish_feature(self, **kwarg):
        self.feature_template.update_publish_feature(self.feature, **kwarg)

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
            and self.dropped_loop_count < self.fault_injection_config.affect_loop.drop
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
            < self.fault_injection_config.affect_receive.drop
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
