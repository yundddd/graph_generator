import csv
import heapq
import os
import random
from dataclasses import dataclass
from typing import List

import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.animation import FuncAnimation

from graph_generator.fault_injection import FaultInjectionConfig
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
            self._validate_fault_injection_config(fault_injection_config)
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
            FuncAnimation(fig, self._simulate_one_step, interval=100, blit=False)
            plt.show()
        else:
            with open(self.output, mode="a", newline="") as file:
                writer = csv.writer(file)
                while len(self.event_queue):
                    self._simulate_one_step()
                    flattened_features = self._get_all_node_features()
                    print(flattened_features)
                    # Each row corresponds to each graph feature snapshots
                    writer.writerow(flattened_features)

    def _simulate_one_step(self, frame=None):
        if len(self.event_queue) == 0:
            plt.gca().figure.canvas.stop_event_loop()
            return
        cur_event = heapq.heappop(self.event_queue)
        if cur_event.timestamp != self.current_time:
            self.current_time = cur_event.timestamp
            if self.current_time >= self.stop_at:
                print(f"Time limit {self.stop_at} reached.")
                return
            print(f"Time: {self.current_time}")
        if isinstance(cur_event.work, LoopConfig):
            # If it's a periodic event, schedule the next one.
            loop = cur_event.work
            assert loop
            self._schedule_next_periodic_work(loop, cur_event.node)
            # Execute callback for this loop:
            print(f"    {cur_event.node} executing loop callback")
            cur_event.node.update_event_feature(
                event=loop, timestamp=cur_event.timestamp
            )
            self._execute_callback(loop.callback)
        else:
            # If it's a subscription event, execute the callback
            data = cur_event.subscription_data
            assert data is not None
            sub = cur_event.work
            print(f"    {cur_event.node} executing subscription callback")
            cur_event.node.update_event_feature(
                event=sub, timestamp=cur_event.timestamp
            )
            if sub.valid_range[0] <= data <= sub.valid_range[1]:
                cur_event.node.update_callback_feature(callback=sub.nominal_callback)
                self._execute_callback(sub.nominal_callback)
            else:
                cur_event.node.update_callback_feature(
                    callback=sub.invalid_input_callback
                )
                self._execute_callback(sub.invalid_input_callback)

    def _schedule_next_periodic_work(self, loop: LoopConfig, node: Node):
        new_event = Event(
            timestamp=self.current_time + loop.period, node=node, work=loop
        )
        heapq.heappush(self.event_queue, new_event)

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
