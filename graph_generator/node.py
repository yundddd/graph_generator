from __future__ import annotations

from collections import defaultdict, deque
from enum import Enum, auto
from typing import Any, List, Tuple, Type

from strict_base_model import StrictBaseModel

from graph_generator.fault_injection import (
    DelayLoopConfig,
    DelayReceiveConfig,
    DropLoopConfig,
    DropPublishConfig,
    DropReceiveConfig,
    FaultConfig,
    MutatePublishConfig,
)


class PublishConfig(StrictBaseModel):
    """
    PublishConfig defines that a node will publish to a topic with a value defined by
    value_range. The delay_range models any transmission delay (unit-less)
    """

    topic: str
    value_range: Tuple[int, int]
    delay_range: Tuple[int, int] = (0, 0)


class CallbackConfig(StrictBaseModel):
    """
    A CallbackConfig defines what to do when a node performs a work.
    """

    # trigger publish to other nodes
    publish: List[PublishConfig] | None = None
    # trigger fault code paths
    fault: FaultConfig | None = None
    # nothing to do
    noop: bool | None = False


class NominalCallbackConfig(CallbackConfig):
    pass


class InvalidInputCallbackConfig(CallbackConfig):
    pass


class LostInputCallbackConfig(CallbackConfig):
    pass


class LoopCallbackConfig(CallbackConfig):
    pass


class SubscriptionConfig(StrictBaseModel):
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


class LoopConfig(StrictBaseModel):
    period: int
    callback: CallbackConfig


class NodeConfig(StrictBaseModel):
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


class NodeFaultInjectionState:
    def __init__(self, config: FaultConfig):
        self.fault_config = config

        self.action_count = 0

        self.done = False

    def handle_action(
        self,
        config_attr: str,
        config_type: Type,
        count_attr: str,
        return_attr: str | None = None,
        cur_time: int | None = None,
    ) -> int | None:
        """
        General handler for actions like delay, drop, or mutate.
        :param config_attr: Attribute in fault_config to check (e.g., "affect_loop").
        :param config_type: Expected type of the configuration (e.g., DropLoopConfig).
        :param count_attr: Attribute in the config to use for comparison (e.g., "drop" or "count").
        :param return_attr: Optional attribute to return (e.g., "delay" or "value").
        :param cur_time: Optional current time for delay calculations.
        :return: Optional integer result, such as a delay time or mutation value.
        """
        config = getattr(self.fault_config, config_attr)
        assert config and isinstance(config, config_type)

        self.action_count += 1
        if self.action_count == getattr(config, count_attr):
            self.done = True

        if return_attr:
            result = getattr(config, return_attr)
            return result + cur_time if cur_time is not None else result
        return None

    def crash(self) -> None:
        self.done = True

    def drop_loop(self) -> None:
        self.handle_action("affect_loop", DropLoopConfig, "drop")

    def delay_loop(self, cur_time: int) -> int:
        ret = self.handle_action(
            "affect_loop", DelayLoopConfig, "count", "delay", cur_time
        )
        assert ret is not None
        return ret

    def delay_receive(self, cur_time: int) -> int:
        ret = self.handle_action(
            "affect_receive", DelayReceiveConfig, "count", "delay", cur_time
        )
        assert ret is not None
        return ret

    def drop_receive(self) -> None:
        self.handle_action("affect_receive", DropReceiveConfig, "drop")

    def drop_publish(self) -> None:
        self.handle_action("affect_publish", DropPublishConfig, "drop")

    def mutate_publish(self) -> int:
        ret = self.handle_action(
            "affect_publish", MutatePublishConfig, "count", "value"
        )
        assert ret is not None
        return ret

    def should_crash(self, cur_time: int) -> bool:
        assert self.fault_config.inject_at
        return (
            cur_time >= self.fault_config.inject_at
            and self.fault_config.crash is not None
            and self.fault_config.crash is True
        )

    def should_drop_loop(self, cur_time: int) -> bool:
        assert self.fault_config.inject_at
        return (
            cur_time >= self.fault_config.inject_at
            and self.fault_config.affect_loop is not None
            and isinstance(self.fault_config.affect_loop, DropLoopConfig)
            and self.action_count < self.fault_config.affect_loop.drop
        )

    def should_delay_loop(self, cur_time: int) -> bool:
        assert self.fault_config.inject_at
        return (
            cur_time >= self.fault_config.inject_at
            and self.fault_config.affect_loop is not None
            and isinstance(self.fault_config.affect_loop, DelayLoopConfig)
            and self.action_count < self.fault_config.affect_loop.count
        )

    def should_drop_receive(self, cur_time: int, topic: str) -> bool:
        assert self.fault_config.inject_at
        return (
            cur_time >= self.fault_config.inject_at
            and self.fault_config.affect_receive is not None
            and isinstance(self.fault_config.affect_receive, DropReceiveConfig)
            and topic == self.fault_config.affect_receive.topic
            and self.action_count < self.fault_config.affect_receive.drop
        )

    def should_delay_receive(self, cur_time: int, topic: str) -> bool:
        assert self.fault_config.inject_at
        return (
            cur_time >= self.fault_config.inject_at
            and self.fault_config.affect_receive is not None
            and isinstance(self.fault_config.affect_receive, DelayReceiveConfig)
            and topic == self.fault_config.affect_receive.topic
            and self.action_count < self.fault_config.affect_receive.count
        )

    def should_drop_publish(self, cur_time: int, topic: str) -> bool:
        assert self.fault_config.inject_at
        return (
            cur_time >= self.fault_config.inject_at
            and self.fault_config.affect_publish is not None
            and isinstance(self.fault_config.affect_publish, DropPublishConfig)
            and topic == self.fault_config.affect_publish.topic
            and self.action_count < self.fault_config.affect_publish.drop
        )

    def should_mutate_publish(self, cur_time: int, topic: str) -> bool:
        assert self.fault_config.inject_at
        return (
            cur_time >= self.fault_config.inject_at
            and self.fault_config.affect_publish is not None
            and isinstance(self.fault_config.affect_publish, MutatePublishConfig)
            and topic == self.fault_config.affect_publish.topic
            and self.action_count < self.fault_config.affect_publish.count
        )


class Node:
    def __init__(self, config: NodeConfig):
        self.config = config
        self.feature_template = NodeFeatureTemplate()
        self.feature = self.feature_template.initial_feature(self.config)
        # Time when the last message was received for a topic.
        self.message_received = defaultdict(int)
        Node._validate_config(config)
        self.pending_faults: deque[NodeFaultInjectionState] = deque()
        self.is_crashed = False

    @property
    def crashed(self) -> bool:
        return self.is_crashed

    def update_event_feature(self, **kwarg):
        self.feature_template.update_event_feature(self.feature, **kwarg)

    def update_publish_feature(self, **kwarg):
        self.feature_template.update_publish_feature(self.feature, **kwarg)

    def update_callback_feature(self, **kwarg):
        self.feature_template.update_callback_feature(self.feature, **kwarg)

    def enqueue_fault_config(self, config: FaultConfig):
        assert (
            config.inject_to == self.config.name
        ), "Cannot inject fault to a node that doesn't match the name"
        self.pending_faults.append(NodeFaultInjectionState(config))

    def crash(self) -> None:
        self.is_crashed = True

    def maybe_drop_loop(self, cur_time: int) -> bool:
        for fault in self.pending_faults:
            if fault.should_drop_loop(cur_time):
                print(
                    f"    \033[91mNode: {self.config.name} dropped loop "
                    f"at {cur_time}\033[0m"
                )
                fault.drop_loop()
                if fault.done:
                    self.pending_faults.remove(fault)
                return True
        return False

    def maybe_delay_loop(self, cur_time: int) -> int | None:
        for fault in self.pending_faults:
            if fault.should_delay_loop(cur_time):
                next_time = fault.delay_loop(cur_time)
                print(
                    "    \033[91mNode: "
                    f"{self.config.name} delayed loop to {next_time}\033[0m"
                )
                if fault.done:
                    self.pending_faults.remove(fault)
                return next_time
        return None

    def maybe_drop_receive(self, cur_time: int, topic: str) -> bool:
        for fault in self.pending_faults:
            if fault.should_drop_receive(cur_time, topic):
                fault.drop_receive()
                print(
                    "    \033[91mNode: "
                    f"{self.config.name} dropped received message from "
                    f"{topic}\033[0m"
                )
                if fault.done:
                    self.pending_faults.remove(fault)
                return True
        return False

    def maybe_delay_receive(self, cur_time: int, topic: str) -> int | None:
        for fault in self.pending_faults:
            if fault.should_delay_receive(cur_time, topic):
                next_time = fault.delay_receive(cur_time)
                print(
                    "    \033[91m"
                    f"[{self.config.name}] delayed received message from "
                    f"{topic} to {next_time}\033[0m"
                )
                if fault.done:
                    self.pending_faults.remove(fault)
                return next_time
        return None

    def maybe_drop_publish(self, cur_time: int, topic: str) -> bool:
        for fault in self.pending_faults:
            if fault.should_drop_publish(cur_time, topic):
                fault.drop_publish()
                print(
                    "    \033[91m"
                    f"[{self.config.name}] dropped published message to "
                    f"{topic}\033[0m"
                )
                if fault.done:
                    self.pending_faults.remove(fault)
                return True
        return False

    def maybe_mutate_publish(self, cur_time: int, topic: str) -> int | None:
        for fault in self.pending_faults:
            if fault.should_mutate_publish(cur_time, topic):
                new_value = fault.mutate_publish()
                print(
                    "    \033[91m"
                    f"[{self.config.name}] mutated published message to "
                    f"{topic}\033[0m"
                )
                if fault.done:
                    self.pending_faults.remove(fault)
                return new_value
        return None

    def maybe_crash(self, cur_time: int) -> bool:
        for fault in self.pending_faults:
            if fault.should_crash(cur_time):
                fault.crash()
                print(
                    "    \033[91m" f"[{self.config.name}] crashed at {cur_time}\033[0m"
                )

                if fault.done:
                    self.pending_faults.remove(fault)
                self.crash()
                return True
        return False

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
        return f"{self.config.name}"
