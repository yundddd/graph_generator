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
    load_config,
)


def main():
    """
    Using basic_config.yaml:
      A
     / \
    B   C
   /     \
  D       E
    """
    try:
        nodes = load_config("~/graph_generator/configs/basic_config.yaml")
    except LoadConfigError as e:
        print(f"Error: {e}")
        exit(1)

    graph = Graph()
    for node in nodes:
        graph.add_node(Node(node))
    graph.build_graph()

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
