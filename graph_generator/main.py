from typing import Type, TypeVar

import yaml

from graph_generator.executor import Executor
from graph_generator.fault_injection import FaultInjectionConfig
from graph_generator.graph import Graph, GraphConfig

T = TypeVar("T")


def config_from_yaml(config_path: str, config_class: Type[T]) -> T:
    with open(config_path, "r") as file:
        return config_class.parse_obj(yaml.safe_load(file))


def main():
    """
      A
     / \
    B   C
   /     \
  D       E
    """
    graph = Graph(config_from_yaml("graph_generator/config/graph.yaml", GraphConfig))

    for i, fault_injection_config in enumerate(
        [
            config_from_yaml(
                "graph_generator/config/delay_loop.yaml", FaultInjectionConfig
            ),
            config_from_yaml(
                "graph_generator/config/delay_receive.yaml", FaultInjectionConfig
            ),
            config_from_yaml(
                "graph_generator/config/drop_loop.yaml", FaultInjectionConfig
            ),
            config_from_yaml(
                "graph_generator/config/drop_receive.yaml", FaultInjectionConfig
            ),
        ]
    ):
        executor = Executor(
            graph=graph,
            stop_at=50,
            fault_injection_config=fault_injection_config,
            output="~/log" + str(i) + ".csv",
        )
        executor.start(viz=False)


if __name__ == "__main__":
    main()
