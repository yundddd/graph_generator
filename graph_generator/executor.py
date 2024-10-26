import csv
import heapq
import os
import random
from dataclasses import dataclass
from typing import List

import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.animation import FuncAnimation

from graph_generator.fault_injection import (
    DelayLoopConfig,
    DelayReceiveConfig,
    DropLoopConfig,
    DropReceiveConfig,
    FaultInjectionConfig,
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
    timestamp: int
    node: Node
    work: LoopConfig | SubscriptionConfig
    subscription_data: int | None = None


class Executor:
    def __init__(
        self,
        *,
        graph: Graph,
        stop_at: int,
        output: str = os.path.expanduser("~/output.csv"),
        fault_injection_config: FaultInjectionConfig | None = None,
    ):
        self.output = output
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
        heapq.heapify(self.event_queue)
        self.current_time = -1
        if os.path.exists(output):
            os.remove(output)
        random.seed(24)

    def start(self, viz: bool = False):
        self._print_sim_summary()
        if viz:
            G = nx.DiGraph()
            for name, _ in self.graph.nodes.items():
                G.add_node(name)
            for src, dests in self.graph.adjacency_list.items():
                for dest in dests:
                    G.add_edge(src.config.name, dest.config.name)
            # Define the layout for the graph
            pos = nx.spectral_layout(G)

            # Initialize the figure and axis
            fig, ax = plt.subplots()
            self.viz_nodes = nx.draw_networkx_nodes(G, pos, node_color="#1f78b4", ax=ax)
            nx.draw_networkx_edges(G, pos, ax=ax)
            nx.draw_networkx_labels(G, pos, ax=ax)

            # returned value should be assigned to keep the animation running
            anim = FuncAnimation(fig, self._simulate_one_step, interval=100, blit=False)

            plt.show()
        else:
            with open(self.output, mode="a", newline="") as file:
                writer = csv.writer(file)
                while len(self.event_queue):
                    if self._simulate_one_step():
                        flattened_features = self._get_all_node_features()
                        # Each row corresponds to each graph feature snapshots
                        writer.writerow(flattened_features)

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

        if isinstance(cur_event.work, LoopConfig):
            return self._handle_loop_work(cur_event)

        return self._handle_subscription_work(cur_event)

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

        # normal case
        self._schedule_next_periodic_work(
            loop, cur_event.node, self.current_time + loop.period
        )
        # Execute callback for this loop:
        print(f"    {cur_event.node} executing loop callback")
        cur_event.node.update_event_feature(event=loop, timestamp=cur_event.timestamp)
        self._execute_callback(loop.callback)
        return True

    def _handle_subscription_work(self, cur_event: Event):
        data = cur_event.subscription_data
        assert data is not None
        sub = cur_event.work
        assert isinstance(sub, SubscriptionConfig)
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

        print(f"    {cur_event.node} executing subscription callback")
        cur_event.node.update_event_feature(event=sub, timestamp=cur_event.timestamp)
        if sub.valid_range[0] <= data <= sub.valid_range[1]:
            if sub.nominal_callback:
                cur_event.node.update_callback_feature(callback=sub.nominal_callback)
                self._execute_callback(sub.nominal_callback)
        else:
            if sub.invalid_input_callback:
                cur_event.node.update_callback_feature(
                    callback=sub.invalid_input_callback
                )
                self._execute_callback(sub.invalid_input_callback)

        return True

    def _schedule_next_periodic_work(
        self, loop: LoopConfig, node: Node, next_time: int
    ):
        new_event = Event(timestamp=next_time, node=node, work=loop)
        heapq.heappush(self.event_queue, new_event)

    def _requeue_work(self, cur_event: Event, next_time: int):
        cur_event.timestamp = next_time
        heapq.heappush(self.event_queue, cur_event)

    def _execute_callback(self, callback: CallbackConfig):
        if callback.publish:
            for pub in callback.publish:
                # publish message to all subscribers of this topic
                for sub_node in self.graph.topic_subscribers(pub.topic):
                    print(f"        publish to {sub_node.config.name}")

                    new_event = Event(
                        timestamp=self.current_time + random.randint(*pub.delay_range),
                        node=sub_node,
                        work=self._find_sub_config(sub_node.config, pub.topic),
                        subscription_data=random.randint(*pub.value_range),
                    )
                    heapq.heappush(self.event_queue, new_event)

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

    def _process_fault_injection_config(self, config: FaultInjectionConfig) -> None:
        self._validate_fault_injection_config(config)
        self.graph.nodes[config.inject_to].fault_injection_config = config

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
                    f"Cannot inject loop fault to a node without loop: " "{node}"
                )

        if (
            config.affect_publish
            and node
            != self.graph.topic_publisher_map[config.affect_publish.topic].config.name
        ):
            raise ValueError(
                f"Cannot inject publish fault to "
                "{node} since it doesn't publish to {config.affect_publish.topic}"
            )
        if config.affect_receive and node not in [
            n.config.name
            for n in self.graph.topic_subscriber_map[config.affect_receive.topic]
        ]:
            raise ValueError(
                f"Cannot inject subscribe fault to "
                "{node} since it doesn't subscribe to {config.affect_receive.topic}"
            )

    def _print_sim_summary(self):
        print(
            "\n\033[92m======== Executing graph with "
            f"{len(self.graph.nodes)} nodes =========\033[0m"
        )
