import glob
import os

import click

from graph_generator.main import handle_main


@click.command()
@click.option("--graph", help="Path to graph config YAML file", type=str, required=True)
@click.option(
    "--output_dir",
    help="Dir to save graph dataset. For each run, the output files contain a node feature file, an edge index file, and the fault label file",
    type=str,
    required=True,
)
@click.option(
    "--fault_dir",
    help="Directory that contains fault injection config files.",
    type=str,
    required=True,
)
@click.option("--stop", help="Stop at max time unit", type=int, required=True)
@click.option(
    "--fault_begin",
    help="Specifies the lower bound time of when the fault is injected",
    type=int,
    required=True,
)
@click.option(
    "--fault_end",
    help="Specifies the upper bound time of when the fault is injected",
    type=int,
    required=True,
)
@click.option(
    "--max_num_sweep",
    help="Number of runs for each fault injected between fault_being and fault_end. The inject_at time will be equally distributed between the fault_begin and fault_end. Duplicates will be removed.",
    type=int,
    required=True,
)
def main(
    graph: str,
    stop: int,
    output_dir: str,
    fault_dir: str,
    fault_begin: int,
    fault_end: int,
    max_num_sweep: int,
):
    if fault_begin >= fault_end or fault_end == 0:
        raise ValueError("fault_begin must be less than fault_end and none zero.")
    if fault_begin + max_num_sweep >= fault_end:
        raise ValueError("fault_begin + max_num_sweep must be less than fault_end.")

    injection_time = sorted(
        set(
            round(fault_begin + i * (fault_end - fault_begin) / (max_num_sweep - 1))
            for i in range(max_num_sweep)
        )
    )

    os.makedirs(output_dir, exist_ok=True)

    fault_files = glob.glob(f"{fault_dir}/*.yaml", recursive=False)

    print(f"Injecting {fault_files} at time {injection_time}")

    for fault in fault_files:
        fault_file_name = os.path.splitext(os.path.basename(fault))[0]
        subdir = f"{output_dir}/{fault_file_name}"
        os.makedirs(subdir, exist_ok=True)
        for inject_at in injection_time:
            handle_main(
                graph=graph,
                fault=fault,
                stop=stop,
                edge_index_output=f"{subdir}/edge_index.csv",
                node_feature_output=f"{subdir}/node_feature_inject_at_{inject_at}.csv",
                fault_label_output=f"{subdir}/fault_label_inject_at_{inject_at}.csv",
                inject_at=inject_at,
                viz=False,
            )


if __name__ == "__main__":
    main()
