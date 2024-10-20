from graph_generator.executor import Executor
from graph_generator.fault_injection import (
    DelayLoopConfig,
    DelayReceiveConfig,
    DropLoopConfig,
    DropReceiveConfig,
    FaultInjectionConfig,
)
from graph_generator.graph import Graph
from graph_generator.node import (
    InvalidInputCallbackConfig,
    LoopCallbackConfig,
    LoopConfig,
    LostInputCallbackConfig,
    Node,
    NodeConfig,
    NominalCallbackConfig,
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
            callback=LoopCallbackConfig(
                publish=[
                    PublishConfig(
                        topic="topic1", value_range=(0, 10), delay_range=(0, 2)
                    )
                ]
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
                nominal_callback=NominalCallbackConfig(
                    publish=[
                        PublishConfig(
                            topic="topic2", value_range=(1, 10), delay_range=(0, 2)
                        )
                    ]
                ),
                invalid_input_callback=InvalidInputCallbackConfig(
                    publish=[
                        PublishConfig(
                            topic="topic2", value_range=(10, 20), delay_range=(0, 2)
                        )
                    ]
                ),
                lost_input_callback=LostInputCallbackConfig(
                    publish=[
                        PublishConfig(
                            topic="topic2", value_range=(20, 30), delay_range=(0, 2)
                        )
                    ]
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
                nominal_callback=NominalCallbackConfig(
                    publish=[
                        PublishConfig(
                            topic="topic3", value_range=(1, 10), delay_range=(0, 2)
                        )
                    ]
                ),
                invalid_input_callback=InvalidInputCallbackConfig(
                    publish=[
                        PublishConfig(
                            topic="topic3", value_range=(10, 20), delay_range=(0, 2)
                        )
                    ]
                ),
                lost_input_callback=LostInputCallbackConfig(
                    publish=[
                        PublishConfig(
                            topic="topic3", value_range=(20, 30), delay_range=(0, 2)
                        )
                    ]
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
                nominal_callback=NominalCallbackConfig(),
                invalid_input_callback=InvalidInputCallbackConfig(),
                lost_input_callback=LostInputCallbackConfig(),
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
                nominal_callback=NominalCallbackConfig(),
                invalid_input_callback=InvalidInputCallbackConfig(),
                lost_input_callback=LostInputCallbackConfig(),
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

    for fault_injection_config in [
        FaultInjectionConfig(
            inject_to="A", inject_at=20, affect_loop=DelayLoopConfig(delay=20)
        ),
        FaultInjectionConfig(
            inject_to="B",
            inject_at=20,
            affect_receive=DropReceiveConfig(topic="topic1", times=3),
        ),
        FaultInjectionConfig(
            inject_to="B",
            inject_at=20,
            affect_receive=DelayReceiveConfig(topic="topic1", delay=3),
        ),
        FaultInjectionConfig(
            inject_to="A", inject_at=20, affect_loop=DropLoopConfig(times=3)
        ),
    ]:
        executor = Executor(
            graph=graph, stop_at=50, fault_injection_config=fault_injection_config
        )
        executor.start(viz=False)


if __name__ == "__main__":
    main()
