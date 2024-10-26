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
    CallbackConfig,
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
import os
import yaml
from typing import List, Tuple, Union

use_yaml = True

class LoadConfigError(Exception):
    pass

def construct_publish_config(data: dict) -> PublishConfig:
    data["value_range"] = tuple(data["value_range"])
    data["delay_range"] = tuple(data["delay_range"])
    return PublishConfig(**data)

def construct_callback_config(data: dict) -> CallbackConfig:
    if "publish" in data:
        data["publish"] = [construct_publish_config(pub) for pub in data["publish"]]
    callback_type = data.pop("type", None)
    if callback_type == "nominal":
        return NominalCallbackConfig(**data)
    elif callback_type == "invalid":
        return InvalidInputCallbackConfig(**data)
    elif callback_type == "lost":
        return LostInputCallbackConfig(**data)
    elif callback_type == "loop":
        return LoopCallbackConfig(**data)
    else:
        raise LoadConfigError(f"Unsupported callback type: {callback_type}")
    return CallbackConfig(**data)

def construct_subscription_config(data: dict) -> SubscriptionConfig:
    data["valid_range"] = tuple(data["valid_range"])
    data["nominal_callback"] = construct_callback_config(data["nominal_callback"])
    data["invalid_input_callback"] = construct_callback_config(data["invalid_input_callback"])
    data["lost_input_callback"] = construct_callback_config(data["lost_input_callback"])
    return SubscriptionConfig(**data)

def construct_node_config(data: dict) -> NodeConfig:
    if "loop" in data:
        data["loop"]["callback"] = construct_callback_config(data["loop"]["callback"])
        data["loop"] = LoopConfig(**data["loop"])
    if "subscribe" in data:
        data["subscribe"] = [construct_subscription_config(sub) for sub in data["subscribe"]]
    return NodeConfig(**data)

def load_config(file_path: str) -> List[NodeConfig]:
    expanded_path = os.path.expanduser(file_path)
    if not os.path.isfile(expanded_path):
        raise LoadConfigError(f"Configuration file not found: {expanded_path}")
    with open(expanded_path, 'r') as file:
        config_data = yaml.safe_load(file)
        if "nodes" not in config_data:
            raise LoadConfigError("Missing 'nodes' key in configuration file")
        return [construct_node_config(node) for node in config_data["nodes"]]

def main():
    """
      A
     / \
    B   C
   /     \
  D       E
    """
    if use_yaml:
        print("Using yaml")
        try:
            nodes = load_config('~/graph_generator/configs/basic_config.yaml')
        except LoadConfigError as e:
            print(f"Error: {e}")
    else:
        print("Using nodeconfig directly")
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
        nodes = [node_a, node_b, node_c, node_d, node_e]
    graph = Graph()
    for node in nodes:
        graph.add_node(Node(node))
        print(node)
    graph.build_graph()

    # for fault_injection_config in [
    #     FaultInjectionConfig(
    #         inject_to="A", inject_at=20, affect_loop=DelayLoopConfig(delay=20)
    #     ),
    #     FaultInjectionConfig(
    #         inject_to="B",
    #         inject_at=20,
    #         affect_receive=DropReceiveConfig(topic="topic1", times=3),
    #     ),
    #     FaultInjectionConfig(
    #         inject_to="B",
    #         inject_at=20,
    #         affect_receive=DelayReceiveConfig(topic="topic1", delay=3),
    #     ),
    #     FaultInjectionConfig(
    #         inject_to="A", inject_at=20, affect_loop=DropLoopConfig(times=3)
    #     ),
    # ]:
    #     executor = Executor(
    #         graph=graph, stop_at=50, fault_injection_config=fault_injection_config
    #     )
    #     executor.start(viz=False)


if __name__ == "__main__":
    main()
