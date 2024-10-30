from typing import Type, TypeVar

import click
import yaml

from graph_generator.executor import Executor
from graph_generator.fault_injection import FaultInjectionConfig
from graph_generator.graph import Graph, GraphConfig

T = TypeVar("T")


def config_from_yaml(config_path: str, config_class: Type[T]) -> T:
    with open(config_path, "r") as file:
        return config_class.parse_obj(yaml.safe_load(file))


@click.command()
@click.option("--graph", help="Path to graph config YAML file")
@click.option(
    "--fault", multiple=True, help="Paths to fault injection config YAML files"
)
@click.option("--viz", help="Visualize the graph", is_flag=True, default=False)
@click.option("--stop", help="Stop at max time unit", default=50)
@click.option(
    "--edge_index_output",
    help="Path to save graph edge index. Each line of the output contains one edge that "
    "is in the form of src,dest. The index for each node is deterministically assigned and "
    "is consistent with the node feature output. Executor will terminate without running.",
    default=None,
)
@click.option(
    "--fault_label_output",
    help="Path to save fault injection information. The output file will contain "
    "a single line in the form of node_index,fault_injection_time. The "
    "node_index corresponds to the node that was injected with the fault and the value"
    "is consistent with the edge index output.",
)
@click.option(
    "--node_feature_output",
    help="Path to save graph node feature. Each line of the output contains all nodes' "
    "features, in the order that is consistent with the edge index output. This must "
    "be specified if --fault option is used",
    default=None,
)
def main(
    graph: str,
    fault: list[str],
    viz: bool,
    stop: int,
    edge_index_output: str,
    node_feature_output: str | None,
    fault_label_output: str,
):
    """
      A
     / \
    B   C
   /     \
  D       E
    """
    if fault and not fault_label_output:
        raise ValueError("Must specify --fault_label_output when using --fault")

    graph_obj = Graph(config_from_yaml(graph, GraphConfig))
    if edge_index_output:
        # dump edge index for the specified graph and terminate.
        graph_obj.dump_edge_index(edge_index_output)
        print("Dumped edge index to", edge_index_output)
        return

    fault_injection_configs = (
        [config_from_yaml(config, FaultInjectionConfig) for config in fault]
        if fault
        else []
    )

    if fault_injection_configs:
        for i, fault_injection_config in enumerate(fault_injection_configs):
            executor = Executor(
                graph=graph_obj,
                stop_at=stop,
                fault_injection_config=fault_injection_config,
                output=(
                    node_feature_output + "_" + str(i) if node_feature_output else None
                ),
            )
            executor.start(viz=viz)

            fault_injection_config.dump(
                index=graph_obj.node_index(fault_injection_config.inject_to),
                output=fault_label_output + "_" + str(i),
            )
    else:
        executor = Executor(
            graph=graph_obj,
            stop_at=stop,
            output=node_feature_output,
        )
        executor.start(viz=viz)


if __name__ == "__main__":
    main()
