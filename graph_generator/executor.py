import csv
import enum
import heapq
import os
import random
from dataclasses import dataclass
from typing import List

import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.animation import FuncAnimation

from graph_generator.fault_injection import FaultConfig
from graph_generator.graph import Graph
from graph_generator.node import (
    CallbackConfig,
    InvalidInputCallbackConfig,
    LoopConfig,
    LostInputCallbackConfig,
    Node,
    NodeConfig,
    NominalCallbackConfig,
    SubscriptionConfig,
)


class NodeColor(enum.Enum):
    NORMAL = "blue"
    FAULTY = "red"


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


def event_to_str(event: LoopConfig | SubscriptionConfig | Event.WatchDogConfig) -> str:
    if isinstance(event, LoopConfig):
        return "loop"
    elif isinstance(event, SubscriptionConfig):
        return f"message from {event.topic}"
    else:
        return f"watchdog on {event.sub.topic}"


class Executor:
    def __init__(
        self,
        *,
        graph: Graph,
        stop_at: int,
        output: str | None = None,
        fault_config: FaultConfig | None = None,
    ):
        """
        Initializes the Executor with the given graph, stop time, optional output file,
        and optional fault injection configuration.

        Args:
            graph (Graph): The graph to be executed.
            stop_at (int): The simulation stop time.
            output (str | None, optional): The output file path for logging results. Defaults to None.
            fault_config (FaultConfig | None, optional): Configuration for fault injection. Defaults to None.
        """
        self.current_time = 0
        self.graph = graph
        self.stop_at = stop_at
        if fault_config:
            self._process_fault_config(fault_config)
            self.fault_config = fault_config

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
                    self._maybe_enqueue_watchdog_work(node, sub, -1)

        heapq.heapify(self.event_queue)

        self.output = None
        if output:
            self.output = os.path.expanduser(output)
            if os.path.exists(output):
                os.remove(output)
        random.seed(24)
        # number of times a plot is drawn. It's used to speed up the visualization.
        self.draw = 0

    def start(self, viz: bool = False):
        """
        Starts the simulation. If `viz` is True, displays the simulation graphically using matplotlib.
        If `output` is specified, logs the simulation results to the specified file.

        Args:
            viz (bool, optional): Whether to display the simulation graphically. Defaults to False.
        """
        self._print_sim_summary()
        self.viz = viz
        if viz:
            self.G = nx.DiGraph()
            for name, _ in self.graph.nodes.items():
                self.G.add_node(name)
            for src, dests in self.graph.adjacency_list.items():
                for dest in dests:
                    self.G.add_edge(src.config.name, dest.config.name)

            self.networkx_nodes = list(self.G.nodes)
            self.node_colors = [NodeColor.NORMAL.value] * len(self.networkx_nodes)
            self.pos = nx.spring_layout(self.G, k=5, iterations=200, seed=24)

            # Initialize the figure and axis
            fig, self.ax = plt.subplots(figsize=(12, 10))
            nx.draw_networkx_nodes(self.G, self.pos, node_color="blue", ax=self.ax)
            nx.draw_networkx_edges(self.G, pos=self.pos, ax=self.ax)
            self.label_pos = {
                node: (coord[0], coord[1] + 0.08) for node, coord in self.pos.items()
            }
            nx.draw_networkx_labels(self.G, pos=self.label_pos, ax=self.ax)
            self.timestamp_text = self.ax.text(
                0, 1, "Time: 0", transform=self.ax.transAxes, ha="left", va="top"
            )

            # returned value should be assigned to keep the animation running
            anim = FuncAnimation(
                fig,
                self._simulate_one_step,
                interval=1,
                blit=False,
                cache_frame_data=True,
                repeat=False,
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

    def _update_node_colors(self, node_idx: int, color: NodeColor):
        if self.viz and self.node_colors[node_idx] != color.value:
            self.node_colors[node_idx] = color.value
            if self.draw == 20:
                # redraw everything to speed up the animation.
                self.draw = 0
                plt.cla()
                nx.draw_networkx_edges(self.G, pos=self.pos, ax=self.ax)
                nx.draw_networkx_labels(self.G, pos=self.label_pos, ax=self.ax)
                self.timestamp_text = self.ax.text(
                    0,
                    1,
                    f"Time: {self.current_time} ",
                    transform=self.ax.transAxes,
                    ha="left",
                    va="top",
                )
                for idx in range(len(self.networkx_nodes)):
                    nx.draw_networkx_nodes(
                        self.G,
                        self.pos,
                        nodelist=[self.networkx_nodes[idx]],
                        node_color=self.node_colors[idx],
                        ax=self.ax,
                    )
            else:
                # just redraw one node.
                self.draw += 1
                nx.draw_networkx_nodes(
                    self.G,
                    self.pos,
                    nodelist=[self.networkx_nodes[node_idx]],
                    node_color=self.node_colors[node_idx],
                    ax=self.ax,
                )

    def _node_index(self, node: Node) -> int:
        return self.graph.node_index(node.config.name)

    def _simulate_one_step(self, frame=None):
        """
        Returns:
            bool: True if a node has executed work. False when no work
            has been done and no feature has changed.
        """
        if self.viz:
            self.timestamp_text.set_text(f"Time: {self.current_time}")
        if len(self.event_queue) == 0:
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

        if cur_event.node.crashed or cur_event.node.maybe_crash(self.current_time):
            assert cur_event.work
            # node has crashed so no need to handle this event.
            print(
                f"    \033[91m[{cur_event.node}] has crashed and "
                f"dropped {event_to_str(cur_event.work)}\033[0m"
            )
            self._update_node_colors(self._node_index(cur_event.node), NodeColor.FAULTY)
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
        assert loop

        # handle fault injection first
        next_time = cur_event.node.maybe_delay_loop(self.current_time)
        if next_time is not None:
            # since the work goes straight back into the queue, we pretend that it didn't do any work and earlyreturn
            self._schedule_next_periodic_work(loop, cur_event.node, next_time)
            self._update_node_colors(self._node_index(cur_event.node), NodeColor.FAULTY)
            return False
        if cur_event.node.maybe_drop_loop(self.current_time):
            # the current work is dropped but the next one is scheduled.
            self._schedule_next_periodic_work(
                loop, cur_event.node, self.current_time + loop.period
            )
            self._update_node_colors(self._node_index(cur_event.node), NodeColor.FAULTY)
            return False

        self._schedule_next_periodic_work(
            loop, cur_event.node, self.current_time + loop.period
        )
        # Execute callback for this loop:
        print(f"    [{cur_event.node}] executing loop callback")
        cur_event.node.update_event_feature(event=loop, timestamp=cur_event.timestamp)
        self._execute_callback(cur_event.node, loop.callback)
        self._update_node_colors(self._node_index(cur_event.node), NodeColor.NORMAL)
        return True

    def _handle_subscription_work(self, cur_event: Event):
        data = cur_event.subscription_data
        assert data is not None
        sub = cur_event.work
        assert isinstance(sub, SubscriptionConfig)
        # handle fault injection first
        if cur_event.node.maybe_drop_receive(self.current_time, sub.topic):
            self._update_node_colors(self._node_index(cur_event.node), NodeColor.FAULTY)
            return False
        next_time = cur_event.node.maybe_delay_receive(self.current_time, sub.topic)
        if next_time is not None:
            # requeue the subscription work to future.
            self._requeue_work(cur_event, next_time)
            self._update_node_colors(self._node_index(cur_event.node), NodeColor.FAULTY)
            return False

        cur_event.node.receive_message(self.current_time, sub.topic)
        cur_event.node.update_event_feature(event=sub, timestamp=cur_event.timestamp)
        if sub.valid_range[0] <= data <= sub.valid_range[1]:
            callback = (
                sub.nominal_callback
                if sub.nominal_callback
                else NominalCallbackConfig(noop=True)
            )
            print(
                f"    [{cur_event.node}] executing nominal input callback for "
                f"{sub.topic}"
            )
            cur_event.node.update_callback_feature(callback=callback)
            self._execute_callback(cur_event.node, callback)
            self._update_node_colors(self._node_index(cur_event.node), NodeColor.NORMAL)
        else:
            callback = (
                sub.invalid_input_callback
                if sub.invalid_input_callback
                else InvalidInputCallbackConfig(noop=True)
            )
            cur_event.node.update_callback_feature(callback=callback)
            print(
                f"    \033[91m[{cur_event.node}] executing invalid input callback "
                f"for {sub.topic}\033[0m"
            )
            self._execute_callback(cur_event.node, callback)
            self._update_node_colors(self._node_index(cur_event.node), NodeColor.FAULTY)

        return True

    def _handle_watchdog_work(self, cur_event: Event):
        watchdog = cur_event.work
        assert isinstance(watchdog, Event.WatchDogConfig)
        data = cur_event.subscription_data
        assert data is not None
        print(
            f"    [{cur_event.node}] executing watchdog callback on topic "
            f"{watchdog.sub.topic}"
        )

        last_receive = cur_event.node.message_received[watchdog.sub.topic]
        if last_receive == data:
            # If last message receipt time is still the same when the watchdog
            # was configured, it means we have not received anything.
            print(
                f"    \033[91m[{cur_event.node}] executing lost input callback "
                f"for {watchdog.sub.topic}\033[0m"
            )
            callback = (
                watchdog.sub.lost_input_callback
                if watchdog.sub.lost_input_callback
                else LostInputCallbackConfig(noop=True)
            )
            self._execute_callback(cur_event.node, callback)
            self._maybe_enqueue_watchdog_work(cur_event.node, watchdog.sub, data)
            self._update_node_colors(self._node_index(cur_event.node), NodeColor.FAULTY)
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
                publish_value = random.randint(*pub.value_range)

                # handle fault injection first
                if node.maybe_drop_publish(self.current_time, pub.topic):
                    self._update_node_colors(self._node_index(node), NodeColor.FAULTY)
                    continue
                new_value = node.maybe_mutate_publish(self.current_time, pub.topic)
                if new_value is not None:
                    publish_value = new_value
                    self._update_node_colors(self._node_index(node), NodeColor.FAULTY)
                else:
                    self._update_node_colors(self._node_index(node), NodeColor.NORMAL)

                node.update_publish_feature()
                # publish message to all subscribers of this topic
                for sub_node in self.graph.topic_subscribers(pub.topic):
                    recv_time_delta = random.randint(*pub.delay_range)
                    print(
                        f"        publish to [{sub_node.config.name}] via {pub.topic} "
                        f" ETA t={recv_time_delta + self.current_time}"
                    )
                    new_event = Event(
                        timestamp=self.current_time + recv_time_delta,
                        node=sub_node,
                        work=self._find_sub_config(sub_node.config, pub.topic),
                        subscription_data=publish_value,
                    )
                    heapq.heappush(self.event_queue, new_event)
        if callback.fault:
            callback.fault.inject_at = self.current_time
            callback.fault.inject_to = node.config.name
            node.enqueue_fault_config(callback.fault)

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

    def _process_fault_config(self, config: FaultConfig) -> None:
        self._validate_fault_config(config)
        assert (
            config.inject_to
        ), "Fault injection config must specify a target node via inject_to"
        assert (
            config.inject_at
        ), "Fault injection config must specify a time via inject_at"
        self.graph.nodes[config.inject_to].enqueue_fault_config(config)

    def _validate_fault_config(self, config: FaultConfig) -> None:
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
