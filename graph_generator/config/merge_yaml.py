import click
import yaml


def merge_yaml_files(input_files, output_file):
    print("input files ", input_files)
    merged_data = {"nodes": []}

    # Loop through the provided YAML files
    for file_path in input_files:
        with open(file_path, "r") as file:
            data = yaml.safe_load(file)
            # Merge data; extend merged_data with each file's contents
            if isinstance(data, dict):
                merged_data["nodes"].extend(data["nodes"])
            else:
                print(
                    f"Warning: {file_path} does not "
                    "contain a dictionary and will be skipped."
                )

    # Write the merged data to the output file
    with open(output_file, "w") as file:
        yaml.dump(merged_data, file)

    print(
        f"Merged YAML with {len(merged_data['nodes'])} "
        f"nodes and saved to {output_file}"
    )


@click.command()
@click.argument("input_files", nargs=-1, type=click.Path(exists=True))
@click.argument("output_file", type=click.Path())
def main(input_files, output_file):
    """Merge multiple YAML files into a single YAML file."""
    merge_yaml_files(input_files, output_file)


if __name__ == "__main__":
    main()
