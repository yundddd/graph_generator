from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, List, Optional, Tuple

from pydantic import BaseModel

from graph_generator.fault_injection import (
    DelayLoopConfig,
    DelayReceiveConfig,
    DropLoopConfig,
    DropPublishConfig,
    DropReceiveConfig,
    FaultInjectionConfig,
    MutatePublishConfig,
)


class PublishConfig(BaseModel):
    """
    PublishConfig defines that a node will publish to a topic with a value defined by
    value_range. The delay_range models any transmission delay (unit-less)
    """

    topic: str
    value_range: Tuple[int, int]
    delay_range: Tuple[int, int] = (0, 0)


class ActionConfig(BaseModel):
    # Drop x events in the future to simulate a node getting stuck.
    drop_event_for: int | None = None
    # Kill this node for good. No more events will be handled by this node.
    crash: bool | None = None


class CallbackConfig(BaseModel):
    """
    A CallbackConfig defines what to do when a node performs a work.
    """

    publish: List[PublishConfig] | None = None
    action: ActionConfig | None = None


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

    def __lt__(self, other: SubscriptionConfig) -> bool:
        return self.topic < other.topic


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
                if sub.nominal_callback and sub.nominal_callback.publish:
                    ret += len(sub.nominal_callback.publish)
                if sub.invalid_input_callback and sub.invalid_input_callback.publish:
                    ret += len(sub.invalid_input_callback.publish)
                if sub.lost_input_callback and sub.lost_input_callback.publish:
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
        # Time when the last message was received for a topic.
        self.message_received = defaultdict(int)
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

        self.should_drop_event_count = 0
        self.should_crash_at: Optional[int] = None
        # record when and how we should mutate publish
        self.should_mutate_publish_at: Optional[
            Tuple[int, MutatePublishConfig | DropPublishConfig]
        ] = None

    def process_fault_injection_config(self, config: FaultInjectionConfig):
        self.fault_injection_config = deepcopy(config)
        if config.affect_publish:
            self.should_mutate_publish_at = (
                config.inject_at,
                config.affect_publish,
            )
        if config.crash is not None and config.crash:
            self.should_crash_at = config.inject_at

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

    def maybe_drop_event(self, cur_time: int, event: Any):
        if isinstance(event, LoopConfig):
            e = "loop"
        elif isinstance(event, SubscriptionConfig):
            e = f"message from {event.topic}"
        else:
            e = f"watchdog on {event.sub.topic}"
        if self.should_crash_at is not None and cur_time >= self.should_crash_at:
            print(
                f"    \033[91mNode: {self.config.name} crashed and dropped "
                f"{e}\033[0m"
            )
            return True
        if self.should_drop_event_count > 0:
            print(
                f"    \033[91mNode: {self.config.name} is stuck and dropped "
                f"{e}\033[0m"
            )
            self.should_drop_event_count -= 1
            return True
        return False

    def should_mutate_publish(
        self, cur_time: int, topic: str
    ) -> Tuple[bool, MutatePublishConfig | DropPublishConfig | None]:
        """
        Determines if a publish operation should be mutated based on the current time and topic.

        Args:
            cur_time (int): The current time unit.
            topic (str): The topic for which the mutation is being checked.

        Returns:
            Tuple[bool, MutatePublishConfig | DropPublishConfig | None]: A tuple where the first element indicates
            if a mutation should occur, and the second element is the configuration for the mutation or drop,
            or None if no mutation should occur.
        """
        if (
            self.should_mutate_publish_at is not None
            and cur_time >= self.should_mutate_publish_at[0]
            and topic == self.should_mutate_publish_at[1].topic
        ):
            if (
                isinstance(self.should_mutate_publish_at[1], DropPublishConfig)
                and self.should_mutate_publish_at[1].drop > 0
            ):
                print(
                    f"    \033[91mNode: {self.config.name} dropped publish to topic "
                    f"{topic}\033[0m"
                )
                self.should_mutate_publish_at[1].drop -= 1
                return True, self.should_mutate_publish_at[1]
            print(
                f"    \033[91mNode: {self.config.name} mutated publish to topic "
                f"{topic}\033[0m"
            )
            return True, self.should_mutate_publish_at[1]
        return False, None

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

    def receive_message(self, cur_time: int, topic: str):
        self.message_received[topic] = cur_time

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
