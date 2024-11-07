from typing import Type, TypeVar

import click
import yaml

from graph_generator.executor import Executor
from graph_generator.fault_injection import FaultConfig
from graph_generator.graph import Graph, GraphConfig

T = TypeVar("T")


def config_from_yaml(config_path: str, config_class: Type[T]) -> T:
    with open(config_path, "r") as file:
        return config_class.parse_obj(yaml.safe_load(file))


def handle_main(
    graph: str,
    fault: str | None,
    viz: bool,
    stop: int,
    edge_index_output: str,
    node_feature_output: str | None,
    fault_label_output: str | None,
    inject_at: int | None,
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

    if inject_at is not None and not fault:
        raise ValueError("Must specify --fault when using --inject_at")

    graph_obj = Graph(config_from_yaml(graph, GraphConfig))
    if edge_index_output:
        # dump edge index for the specified graph and terminate.
        graph_obj.dump_edge_index(edge_index_output)
        print("Dumped edge index to", edge_index_output)

    fault_config = config_from_yaml(fault, FaultConfig) if fault else None
    if inject_at is not None:
        assert fault_config
        fault_config.inject_at = inject_at

    if fault_config:
        assert fault_config.inject_at
        assert fault_config.inject_to, "Must specify --inject_to"
        if fault_config.inject_at >= stop or fault_config.inject_at <= 0:
            raise ValueError(
                f"Cannot inject fault at a non-positive time or exceeds the stop time {stop}"
            )

    executor = Executor(
        graph=graph_obj,
        stop_at=stop,
        fault_config=fault_config,
        output=node_feature_output,
    )

    executor.start(viz=viz)

    if fault_config and fault_label_output:
        assert fault_config.inject_to
        fault_config.dump(
            index=graph_obj.node_index(fault_config.inject_to),
            output=fault_label_output,
        )


@click.command()
@click.option("--graph", help="Path to graph config YAML file", type=str, required=True)
@click.option(
    "--fault", help="Paths to fault injection config YAML file", type=str, default=None
)
@click.option("--viz", help="Visualize the graph", is_flag=True, default=False)
@click.option("--stop", help="Stop at max time unit", type=int, default=50)
@click.option(
    "--edge_index_output",
    type=str,
    help="Path to save graph edge index. Each line of the output contains one edge that "
    "is in the form of src,dest. The index for each node is deterministically assigned and "
    "is consistent with the node feature output. Executor will terminate without running.",
    default=None,
)
@click.option(
    "--fault_label_output",
    type=str,
    help="Path to save fault injection information. The output file will contain "
    "a single line in the form of node_index,fault_injection_time. The "
    "node_index corresponds to the node that was injected with the fault and the value"
    "is consistent with the edge index output.",
    default=None,
)
@click.option(
    "--node_feature_output",
    type=str,
    help="Path to save graph node feature. Each line of the output contains all nodes' "
    "features, in the order that is consistent with the edge index output. This must "
    "be specified if --fault option is used",
    default=None,
)
@click.option(
    "--inject_at",
    type=int,
    help="Specify the time unit at which to inject the fault, overriding whatever was "
    "specified in the fault injection config. This is useful to generate graphs and perform "
    "a sweep of when to inject faults.",
    default=None,
)
def main(
    graph: str,
    fault: str | None,
    viz: bool,
    stop: int,
    edge_index_output: str,
    node_feature_output: str | None,
    fault_label_output: str | None,
    inject_at: int | None,
):
    handle_main(
        graph=graph,
        fault=fault,
        viz=viz,
        stop=stop,
        edge_index_output=edge_index_output,
        node_feature_output=node_feature_output,
        fault_label_output=fault_label_output,
        inject_at=inject_at,
    )


if __name__ == "__main__":
    main()
