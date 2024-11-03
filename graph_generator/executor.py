import csv
import heapq
import os
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import List

import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.animation import FuncAnimation

from graph_generator.fault_injection import (
    DelayLoopConfig,
    DelayReceiveConfig,
    DropLoopConfig,
    DropPublishConfig,
    DropReceiveConfig,
    FaultInjectionConfig,
    MutatePublishConfig,
)
from graph_generator.graph import Graph
from graph_generator.node import (
    CallbackConfig,
    LoopConfig,
    Node,
    NodeConfig,
    SubscriptionConfig,
)


@dataclass(order=True)
class Event:
    """
    This class represents an event in the event queue. All events are first
    ordered by the timestamp. To break ties, use the node config as well as
    the even priority.
    """

    @dataclass
    class WatchDogConfig:
        sub: SubscriptionConfig

        def __lt__(self, other: "Event.WatchDogConfig"):
            return self.sub < other.sub

    # The timestamp of this event
    timestamp: int
    # The associated Node for this event, which will perform some work
    node: Node
    work_priority: int = 0

    # The type of the work to be performed.
    work: LoopConfig | SubscriptionConfig | WatchDogConfig | None = None
    # The data associated with the subscription. If the work type is WatchDog,
    # this is the last received time of the subscription.
    subscription_data: int | None = None

    def __post_init__(self):
        # Define a priority for each work type
        work_type_priority = {
            LoopConfig: 0,
            SubscriptionConfig: 1,
            Event.WatchDogConfig: 2,
        }
        assert self.work
        object.__setattr__(
            self, "work_priority", work_type_priority.get(type(self.work), -1)
        )


class Executor:
    def __init__(
        self,
        *,
        graph: Graph,
        stop_at: int,
        output: str | None = None,
        fault_injection_config: FaultInjectionConfig | None = None,
    ):
        """
        Initializes the Executor with the given graph, stop time, optional output file,
        and optional fault injection configuration.

        Args:
            graph (Graph): The graph to be executed.
            stop_at (int): The simulation stop time.
            output (str | None, optional): The output file path for logging results. Defaults to None.
            fault_injection_config (FaultInjectionConfig | None, optional): Configuration for fault injection. Defaults to None.
        """
        self.current_time = 0
        self.graph = graph
        self.stop_at = stop_at
        if fault_injection_config:
            self._process_fault_injection_config(fault_injection_config)
            self.fault_injection_config = fault_injection_config

        nodes_with_loop = graph.nodes_with_loops()
        self.event_queue = [
            Event(timestamp=0, node=node, work=node.config.loop)
            for node in nodes_with_loop
            if node.config.loop
        ]
        # Enqueue all the subscription watchdog
        for node in graph.nodes.values():
            if node.config.subscribe:
                for sub in node.config.subscribe:
                    self._maybe_enqueue_watchdog_work(node, sub, 0)

        heapq.heapify(self.event_queue)

        self.output = None
        if output:
            self.output = os.path.expanduser(output)
            if os.path.exists(output):
                os.remove(output)
        random.seed(24)

    def start(self, viz: bool = False):
        """
        Starts the simulation. If `viz` is True, displays the simulation graphically using matplotlib.
        If `output` is specified, logs the simulation results to the specified file.

        Args:
            viz (bool, optional): Whether to display the simulation graphically. Defaults to False.
        """
        self._print_sim_summary()
        if viz:
            G = nx.DiGraph()
            for name, _ in self.graph.nodes.items():
                G.add_node(name)
            for src, dests in self.graph.adjacency_list.items():
                for dest in dests:
                    G.add_edge(src.config.name, dest.config.name)
            # Define the layout for the graph
            pos = nx.spring_layout(G, k=5)

            # Initialize the figure and axis
            fig, ax = plt.subplots()
            self.viz_nodes = nx.draw_networkx_nodes(G, pos, node_color="#1f78b4", ax=ax)
            nx.draw_networkx_edges(G, pos, ax=ax)
            label_pos = {
                node: (coord[0], coord[1] + 0.08) for node, coord in pos.items()
            }
            nx.draw_networkx_labels(G, label_pos, ax=ax)

            # returned value should be assigned to keep the animation running
            anim = FuncAnimation(
                fig,
                self._simulate_one_step,
                interval=100,
                blit=False,
                cache_frame_data=False,
            )

            plt.show()
        else:
            if self.output:
                with open(self.output, mode="a", newline="") as file:
                    writer = csv.writer(file)
                    last_row_feature = None
                    while len(self.event_queue):
                        if self._simulate_one_step():
                            flattened_features = self._get_all_node_features()
                            # deduplicate features. Sometimes a step could only involve
                            # watchdog checks which could lead to no feature update.
                            if flattened_features != last_row_feature:
                                # Each row corresponds to each graph feature snapshots
                                writer.writerow(flattened_features)
                                last_row_feature = flattened_features
            else:
                # just run the simulation without writing to a file
                while len(self.event_queue):
                    self._simulate_one_step()

    def _simulate_one_step(self, frame=None):
        """
        Returns:
            bool: True if a node has executed work. False when no work
            has been done and no feature has changed.
        """
        if len(self.event_queue) == 0:
            plt.gca().figure.canvas.stop_event_loop()
            return False
        cur_event = heapq.heappop(self.event_queue)
        if cur_event.timestamp != self.current_time:
            self.current_time = cur_event.timestamp
            if self.current_time >= self.stop_at:
                print(
                    "\033[92m======== Time limit "
                    f"{self.stop_at} reached ========\033[0m"
                )
                # clear the queue and discard all remaining work.
                self.event_queue = []
                return False
            print(f"Time: {self.current_time}")

        if cur_event.node.is_crashed(self.current_time, cur_event.work):
            # node has crashed so no need to handle this event.
            return False

        if isinstance(cur_event.work, LoopConfig):
            return self._handle_loop_work(cur_event)

        elif isinstance(cur_event.work, SubscriptionConfig):
            return self._handle_subscription_work(cur_event)
        elif isinstance(cur_event.work, Event.WatchDogConfig):
            return self._handle_watchdog_work(cur_event)
        else:
            assert False, "Unknown work type"

    def _handle_loop_work(self, cur_event: Event):
        loop = cur_event.work
        assert isinstance(loop, LoopConfig)
        cur_fault_injection_config = cur_event.node.fault_injection_config
        assert loop

        # handle fault injection first
        if cur_event.node.should_delay_loop(self.current_time):
            assert cur_fault_injection_config
            assert isinstance(cur_fault_injection_config.affect_loop, DelayLoopConfig)

            next_time = self.current_time + cur_fault_injection_config.affect_loop.delay
            cur_event.node.delay_loop(next_time)
            # since the work goes straight back into the queue, we pretend that it didn't do any work and early return
            self._requeue_work(cur_event, next_time)
            return False

        if cur_event.node.should_drop_loop(self.current_time):
            assert cur_fault_injection_config
            assert isinstance(cur_fault_injection_config.affect_loop, DropLoopConfig)

            cur_event.node.drop_loop(self.current_time)
            # the current work is dropped but the next one is scheduled.
            self._schedule_next_periodic_work(
                loop, cur_event.node, self.current_time + loop.period
            )
            return False

        # always schedule the next periodic work.
        self._schedule_next_periodic_work(
            loop, cur_event.node, self.current_time + loop.period
        )

        if not cur_event.node.is_stuck(loop):
            # Execute callback for this loop:
            print(f"    {cur_event.node} executing loop callback")
            cur_event.node.update_event_feature(
                event=loop, timestamp=cur_event.timestamp
            )
            self._execute_callback(cur_event.node, loop.callback)
            return True
        return False

    def _handle_subscription_work(self, cur_event: Event):
        data = cur_event.subscription_data
        assert data is not None
        sub = cur_event.work
        assert isinstance(sub, SubscriptionConfig)

        if cur_event.node.is_stuck(sub):
            return False
        cur_fault_injection_config = cur_event.node.fault_injection_config

        # handle fault injection first
        if cur_event.node.should_drop_receive(self.current_time, sub.topic):
            assert cur_fault_injection_config
            assert isinstance(
                cur_fault_injection_config.affect_receive, DropReceiveConfig
            )
            assert cur_fault_injection_config
            cur_event.node.drop_receive(sub.topic)
            return False

        if cur_event.node.should_delay_receive(self.current_time, sub.topic):
            cur_event.node.delay_receive(sub.topic)
            assert cur_fault_injection_config
            assert isinstance(
                cur_fault_injection_config.affect_receive, DelayReceiveConfig
            )
            # requeue the subscription work to future.
            self._requeue_work(
                cur_event,
                self.current_time + cur_fault_injection_config.affect_receive.delay,
            )
            return False

        cur_event.node.receive_message(self.current_time, sub.topic)
        cur_event.node.update_event_feature(event=sub, timestamp=cur_event.timestamp)
        if sub.valid_range[0] <= data <= sub.valid_range[1]:
            if sub.nominal_callback:
                print(
                    f"    {cur_event.node} executing nominal input callback on "
                    f"topic {sub.topic}"
                )
                cur_event.node.update_callback_feature(callback=sub.nominal_callback)
                self._execute_callback(cur_event.node, sub.nominal_callback)
        else:
            if sub.invalid_input_callback:
                cur_event.node.update_callback_feature(
                    callback=sub.invalid_input_callback
                )
                print(
                    f"    \033[91m{cur_event.node} executing invalid input callback\033[0m "
                    f"on topic {sub.topic}"
                )

                self._execute_callback(cur_event.node, sub.invalid_input_callback)

        return True

    def _handle_watchdog_work(self, cur_event: Event):
        watchdog = cur_event.work
        assert isinstance(watchdog, Event.WatchDogConfig)
        data = cur_event.subscription_data
        assert data is not None
        print(
            f"    {cur_event.node} executing watchdog callback on topic "
            f"{watchdog.sub.topic}"
        )
        if cur_event.node.config.name == "planner":
            print(
                f"planner last received data on {watchdog.sub.topic}: "
                f"{cur_event.node.message_received[watchdog.sub.topic]}"
                f" watchdog data: {data}"
            )
        last_receive = cur_event.node.message_received[watchdog.sub.topic]
        if last_receive == data:
            # If last message receipt time is still the same when the watchdog
            # was configured, it means we have not received anything.
            print(
                f"    \033[91m{cur_event.node} executing lost input callback "
                f"for {watchdog.sub.topic}\033[0m"
            )
            if watchdog.sub.lost_input_callback:
                self._execute_callback(cur_event.node, watchdog.sub.lost_input_callback)
            self._maybe_enqueue_watchdog_work(cur_event.node, watchdog.sub, data)
        else:
            self._maybe_enqueue_watchdog_work(
                cur_event.node, watchdog.sub, last_receive
            )

    def _schedule_next_periodic_work(
        self, loop: LoopConfig, node: Node, next_time: int
    ):
        new_event = Event(timestamp=next_time, node=node, work=loop)
        heapq.heappush(self.event_queue, new_event)

    def _requeue_work(self, cur_event: Event, next_time: int):
        cur_event.timestamp = next_time
        heapq.heappush(self.event_queue, cur_event)

    def _execute_callback(self, node: Node, callback: CallbackConfig):
        if callback.publish:
            for pub in callback.publish:
                mutate_publish = node.should_mutate_publish(
                    cur_time=self.current_time, topic=pub.topic
                )
                if mutate_publish[0] and isinstance(
                    mutate_publish[1], DropPublishConfig
                ):
                    # dropped a publish
                    continue
                publish_value = random.randint(*pub.value_range)
                if mutate_publish[0] and isinstance(
                    mutate_publish[1], MutatePublishConfig
                ):
                    # mutate a publish value
                    publish_value = mutate_publish[1].value

                node.update_publish_feature()
                # publish message to all subscribers of this topic
                for sub_node in self.graph.topic_subscribers(pub.topic):
                    recv_time_delta = random.randint(*pub.delay_range)
                    print(
                        f"        publish to {sub_node.config.name} via {pub.topic} "
                        f" +{recv_time_delta}"
                    )
                    new_event = Event(
                        timestamp=self.current_time + recv_time_delta,
                        node=sub_node,
                        work=self._find_sub_config(sub_node.config, pub.topic),
                        subscription_data=publish_value,
                    )
                    heapq.heappush(self.event_queue, new_event)
        if callback.action:
            if callback.action.drop_event_for is not None:
                node.should_drop_event_count += callback.action.drop_event_for
            if callback.action.crash is not None and callback.action.crash:
                node.should_crash_at = self.current_time

    def _find_sub_config(self, node: NodeConfig, topic: str) -> SubscriptionConfig:
        if not node.subscribe:
            raise ValueError(f"{node.name} doesn't subscribe to anything")
        for sub in node.subscribe:
            if sub.topic == topic:
                return sub
        raise ValueError(f"{node.name} doesn't subscribe to {topic}")

    def _get_all_node_features(self) -> List:
        "get flattened feature list for the entire graph"
        return [item for node in self.graph.nodes.values() for item in node.feature]

    def _maybe_enqueue_watchdog_work(
        self, node: Node, sub: SubscriptionConfig, last_received: int
    ):
        if sub.watchdog is None:
            return
        # wake up and check for lost input
        new_event = Event(
            timestamp=self.current_time + sub.watchdog,
            node=node,
            work=Event.WatchDogConfig(sub=sub),
            subscription_data=last_received,
        )
        heapq.heappush(self.event_queue, new_event)

    def _process_fault_injection_config(self, config: FaultInjectionConfig) -> None:
        self._validate_fault_injection_config(config)
        self.graph.nodes[config.inject_to].process_fault_injection_config(config)

    def _validate_fault_injection_config(self, config: FaultInjectionConfig) -> None:
        self.loop_mutation = []
        self.sub_mutation = []
        self.pub_mutation = []
        node = config.inject_to
        if node not in self.graph.nodes.keys():
            raise ValueError(f"Cannot inject fault to non-existent node {node}")
        if config.affect_loop:
            if node not in [n.config.name for n in self.graph.nodes_with_loops()]:
                raise ValueError(
                    f"Cannot inject loop fault to a node without loop: {node}"
                )

        if (
            config.affect_publish
            and node
            != self.graph.topic_publisher_map[config.affect_publish.topic].config.name
        ):
            raise ValueError(
                "Cannot inject publish fault to "
                f"{node} since it doesn't publish to {config.affect_publish.topic}"
            )
        if config.affect_receive and node not in [
            n.config.name
            for n in self.graph.topic_subscriber_map[config.affect_receive.topic]
        ]:
            raise ValueError(
                "Cannot inject subscribe fault to "
                f"{node} since it doesn't subscribe to {config.affect_receive.topic}"
            )

    def _print_sim_summary(self):
        print(
            "\n\033[92m======== Executing graph with "
            f"{len(self.graph.nodes)} nodes =========\033[0m"
        )
        print("Time: 0")
