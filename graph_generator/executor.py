import heapq
import random
from dataclasses import dataclass

from graph_generator.graph import Graph
from graph_generator.node import (
    CallbackConfig,
    LoopConfig,
    NodeConfig,
    SubscriptionConfig,
)


@dataclass(order=True)
class Event:
    timestamp: int
    node: str
    work: LoopConfig | SubscriptionConfig
    subscription_data: int | None = None


class Executor:
    def __init__(self, graph: Graph):
        random.seed(9001)
        self.graph = graph
        nodes_with_loop = graph.nodes_with_loops()
        self.event_queue = [
            Event(timestamp=0, node=node.name, work=node.loop)
            for node in nodes_with_loop
            if node.loop
        ]
        heapq.heapify(self.event_queue)
        self.current_time = -1

    def start(self, stop_at: int):
        while len(self.event_queue):
            cur_event = heapq.heappop(self.event_queue)
            if cur_event.timestamp != self.current_time:
                self.current_time = cur_event.timestamp
                if self.current_time >= stop_at:
                    print(f"Time limit {stop_at} reached.")
                    break
                print(f"Time: {self.current_time}")

            if isinstance(cur_event.work, LoopConfig):
                # If it's a periodic event, schedule the next one.
                loop = cur_event.work
                assert loop
                self._schedule_next_periodic_work(loop, cur_event.node)
                # Execute callback for this loop:
                print(f"    {cur_event.node} executing loop callback")
                self._execute_callback(loop.callback)

            else:
                data = cur_event.subscription_data
                assert data is not None
                sub = cur_event.work
                print(f"    {cur_event.node} executing subscription callback")
                if sub.valid_range[0] <= data <= sub.valid_range[1]:
                    self._execute_callback(sub.nominal_callback)
                else:
                    self._execute_callback(sub.faulted_callback)

    def _schedule_next_periodic_work(self, loop: LoopConfig, node_name: str):
        new_event = Event(
            timestamp=self.current_time + loop.period, node=node_name,
            work=loop)
        heapq.heappush(self.event_queue, new_event)

    def _execute_callback(self, callback: CallbackConfig):
        if callback.publish:
            for pub in callback.publish:
                # publish message to all subscribers of this topic
                for sub_node in self.graph.topic_subscribers(pub.topic):
                    print(f"        publish to {sub_node.config.name}")

                    new_event = Event(
                        timestamp=self.current_time + random.randint(*pub.delay_range),
                        node=sub_node.config.name,
                        work=self._find_sub_config(sub_node.config, pub.topic),
                        subscription_data=random.randint(*pub.value_range),
                    )
                    heapq.heappush(self.event_queue, new_event)

    def _find_sub_config(
            self, node: NodeConfig, topic: str) -> SubscriptionConfig:
        if not node.subscribe:
            raise ValueError(f"{node.name} doesn't subscribe to anything")
        for sub in node.subscribe:
            if sub.topic == topic:
                return sub
        raise ValueError(f"{node.name} doesn't subscribe to {topic}")
