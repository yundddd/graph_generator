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
cd ~/graph_generator
bazel run //graph_generator:main
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
