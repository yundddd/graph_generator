# Setup

Clone the repo with:

```
cd ~
git clone https://github.com/yundddd/graph_generator.git
```

Install [bazel](https://bazel.build/install) to get hermetic and reproducible builds.

# Define Graph Structure

See `graph_generator/main` for a default graph.

# Run the generator

Execute the following command to generate an execution graph based on the defined structure:

```
# ensure we are at the repo root
cd ~/graph_generator
```

Dump the edge index for the graph defined by graph.yaml to a file:

```
bazel run //graph_generator:main -- --graph graph_generator/config/graph.yaml --edge_index_output ~/edge
```

Run graph executor based on graph.yaml and stop at time unit 50, save node features to a file:

```
bazel run //graph_generator:main -- --graph graph_generator/config/graph.yaml --node_feature_output ~/out --stop 50
```

Run graph executor twice. The first run injects a fault specified in delay\*loop.yaml. The second time injects a fault specified in delay_receive.yaml. The output file name will be appended with monotonically increasing integer. For example, ~/out1 corresponds to the first run and ~/out2 corresponds to the second run. The --fault_label_output must be specified to capture where and when a fault was injected. The output file will also be appended with monotonically increasing integer and it's content contains a single line in the form of node_index,fault_injection_time.

```
bazel run //graph_generator:main -- --graph graph_generator/config/graph.yaml --node_feature_output ~/out --fault graph_generator/config/delay_loop.yaml --fault graph_generator/config/delay_receive.yaml --fault_label_output ~/fault_label
```

# Lint

Remember to apply lint before submitting PRs. The max line length for this repo is 88.

```
# At project root
./lint.sh
```

# TODO

0 - Proposal
1 - Use YAML configuration instead of dataclasses for composing graphs. [Alycia]
2 - Fault Injection feature [Tianyang]
3 - Training pipeline [Tracy]
4 - Visualization
5 - Random graph generation
