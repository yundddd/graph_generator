import csv
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List

import matplotlib.pyplot as plt
import networkx as nx
from pydantic import BaseModel

from graph_generator.node import CallbackConfig, Node, NodeConfig


@dataclass
class GraphConfig(BaseModel):
    nodes: List[NodeConfig]


class Graph:
    def __init__(self, config: GraphConfig):
        self.config = config
        self.nodes = dict()
        self.topic_publisher_map = dict()
        self.topic_subscriber_map = defaultdict(list)
        self.adjacency_list = defaultdict(list)

        for node in config.nodes:
            self._add_node(Node(node))

        self._build_graph()

    def dump_edge_index(self, output: str):
        output = os.path.expanduser(output)
        if os.path.exists(output):
            os.remove(output)
        node_to_index = {node: i for i, node in enumerate(self.nodes.values())}

        with open(output, mode="a", newline="") as file:
            writer = csv.writer(file)
            for src, dests in self.adjacency_list.items():
                for dest in dests:
                    writer.writerow([node_to_index[src], node_to_index[dest]])

    def _add_node(self, node: Node):
        if node.config.name in self.nodes.keys():
            raise ValueError(f"Node name must be unique: {node.config.name}")
        self.nodes[node.config.name] = node

    def _build_graph(self):
        for _, node in self.nodes.items():
            if node.config.loop:
                loop = node.config.loop
                if not loop.callback.publish:
                    continue
                for publish in loop.callback.publish:
                    self._add_publisher(publish.topic, publisher=node)

            if node.config.subscribe:
                for sub in node.config.subscribe:
                    self._add_subscriber(topic=sub.topic, subscriber=node)
                    if sub.nominal_callback:
                        self._add_publisher_from_callback(node, sub.nominal_callback)
                    if sub.invalid_input_callback:
                        self._add_publisher_from_callback(
                            node, sub.invalid_input_callback
                        )
                    if sub.lost_input_callback:
                        self._add_publisher_from_callback(node, sub.lost_input_callback)

        for topic, publisher in self.topic_publisher_map.items():
            for subscriber in self.topic_subscriber_map[topic]:
                self.adjacency_list[publisher].append(subscriber)

    def visualize(self):
        G = nx.DiGraph()
        for name, _ in self.nodes.items():
            G.add_node(name)
        for src, dests in self.adjacency_list.items():
            for dest in dests:
                G.add_edge(src.config.name, dest.config.name)
        nx.draw_spectral(G, with_labels=True)
        plt.show()

    def nodes_with_loops(self):
        return [node for _, node in self.nodes.items() if node.config.loop]

    def topic_subscribers(self, topic: str) -> List[Node]:
        return self.topic_subscriber_map.get(topic, [])

    def topic_publisher(self, topic: str) -> Node | None:
        return self.topic_publisher_map.get(topic, None)

    def _add_publisher(self, topic: str, publisher: Node):
        if (
            topic in self.topic_publisher_map.keys()
            and self.topic_publisher_map[topic] != publisher
        ):
            raise ValueError(
                f"Duplicate publisher for topic {topic}: "
                "{self.topic_publisher_map[topic]} and {publisher}"
            )
        self.topic_publisher_map[topic] = publisher

    def _add_subscriber(self, topic: str, subscriber: Node):
        if subscriber in self.topic_subscriber_map[topic]:
            raise ValueError(f"Duplicate subscriber " "{subscriber} for topic {topic}")
        self.topic_subscriber_map[topic].append(subscriber)

    def _add_publisher_from_callback(self, node: Node, callback: CallbackConfig):
        if callback.publish:
            for publish in callback.publish:
                self._add_publisher(topic=publish.topic, publisher=node)

    topic_publisher_map: dict[str, Node]
    topic_subscriber_map: defaultdict[str, List[Node]]
    adjacency_list: defaultdict[Node, List[Node]]
    nodes: Dict[str, Node]
