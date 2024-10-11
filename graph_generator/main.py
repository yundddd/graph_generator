from graph_generator.executor import Executor
from graph_generator.graph import Graph
from graph_generator.node import (
    CallbackConfig,
    LoopConfig,
    Node,
    NodeConfig,
    PublishConfig,
    SubscriptionConfig,
)


def main():
    """
      A
     / \
    B   C
   /     \
  D       E
    """
    node_a = NodeConfig(
        name="A",
        loop=LoopConfig(
            period=10,
            callback=CallbackConfig(
                publish=[PublishConfig(topic="topic1", value_range=(0, 10))]
            ),
        ),
    )
    node_b = NodeConfig(
        name="B",
        subscribe=[
            SubscriptionConfig(
                topic="topic1",
                valid_range=(0, 10),
                watchdog=2,
                nominal_callback=CallbackConfig(
                    publish=[PublishConfig(topic="topic2", value_range=(1, 10))]
                ),
                faulted_callback=CallbackConfig(
                    publish=[PublishConfig(topic="topic2", value_range=(10, 20))]
                ),
                watchdog_callback=CallbackConfig(
                    publish=[PublishConfig(topic="topic2", value_range=(20, 30))]
                ),
            )
        ],
    )
    node_c = NodeConfig(
        name="C",
        subscribe=[
            SubscriptionConfig(
                topic="topic1",
                valid_range=(0, 10),
                watchdog=2,
                nominal_callback=CallbackConfig(
                    publish=[PublishConfig(topic="topic3", value_range=(1, 10))]
                ),
                faulted_callback=CallbackConfig(
                    publish=[PublishConfig(topic="topic3", value_range=(10, 20))]
                ),
                watchdog_callback=CallbackConfig(
                    publish=[PublishConfig(topic="topic3", value_range=(20, 30))]
                ),
            )
        ],
    )
    node_d = NodeConfig(
        name="D",
        subscribe=[
            SubscriptionConfig(
                topic="topic2",
                valid_range=(0, 10),
                watchdog=2,
                nominal_callback=CallbackConfig(),
                faulted_callback=CallbackConfig(),
                watchdog_callback=CallbackConfig(),
            )
        ],
    )
    node_e = NodeConfig(
        name="E",
        subscribe=[
            SubscriptionConfig(
                topic="topic3",
                valid_range=(0, 10),
                watchdog=2,
                nominal_callback=CallbackConfig(),
                faulted_callback=CallbackConfig(),
                watchdog_callback=CallbackConfig(),
            )
        ],
    )
    graph = Graph()
    graph.add_node(Node(node_a))
    graph.add_node(Node(node_b))
    graph.add_node(Node(node_c))
    graph.add_node(Node(node_d))
    graph.add_node(Node(node_e))
    graph.build_graph()
    print(graph.adjacency_list)
    graph.visualize()

    executor = Executor(graph)
    executor.start(stop_at=50)


if __name__ == "__main__":
    main()
