# Graph Executor

<img src="graph_executor.png" alt="Graph Executor" width="500"/>

This repo implements a config-driven graph executor in `/graph_generator` that can be used to generate time series graphs modeling a system of publish-subscribe relationships with injected faults at random timepoints. It also contains datasets in `/graph_generator/dataset` created using the executor that are used to train and evaluate GNN methods on Root Cause Analysis (RCA), as well as GNN model experimentation pipelines in `/notebooks` with results.

In software engineering, a common technique to increase test-ability and achieve separation of concerns in large-scale systems is to organize software into independent modules. When connecting multiple modules via some communication medium, they collaborate and work to achieve the same goal. For example, open-source frameworks such as [Apache Airflow](https://airflow.apache.org/) or [Robotic Operation Systems](https://www.ros.org/), allow users to organize software into dependent units to form data processing pipelines. This network of software modules could be modeled as a directed cyclic graph: each node represents a module, which consumes input from other modules and produces output for downstream nodes. However, this architecture suffers from the issue of cascading failure, where one node failing could lead to downstream nodes failing in a cascading manner. Failures may manifest in different forms, such as a node receiving invalid input and generating garbage output or becoming completely silent due to a software crash. For complex graphs, troubleshooting becomes difficult when users need to handle a flood of log data or alerts and may require specialized domain knowledge to localize the root cause efficiently. Therefore, a method to predict or identify the root cause when failures occur is essential to maintaining system reliability and minimizing downtime.

In our literature review, we found that real-world data that captures such failing scenarios is often proprietary. Most RCA-related publications we came across used proprietary datasets or simulated their data, but did not provide simulation code nor sufficient details on how faults were injected. Therefore, we developed a graph executor simulator that allows us to generate graph features and inject faults in a controlled and systematic manner. Given a set of nodes and edges, with each edge representing a publish-subscribe relationship between nodes, the simulator generates node features of the graph at each time point based on a predefined rule provided by users. For example, users may define what a node does if it receives an invalid input, and responds by sending appropriate outputs to other nodes. If this occurs, the node could produce bad outputs which will immediately affect its neighboring nodes, and propagate to the entire graph over time.

The graph executor can simulate scenarios based on customized config to generate a time series of graph data that can be used to train machine learning models that can tackle RCA.

## Visualization

We created a graph configuration that approximates modern autonomous vehicle software [architecture](https://github.com/yundddd/graph_generator/tree/master/graph_generator/config/autonomous_vehicle) (with reasonably similar topology), and injected different faults to the graph at different times to collect a large amount of graph data. The executor is capable of generating visualizations for users to understand dynamic graph systems. Blue nodes denote nominal nodes while red nodes denote faulted nodes.
For example, autonomous vehicle software stacks (AV 1.0) typically include sensor, mapping, perception, motion planner and control subsystems. When we crash a camera sensor module, which is the lowest layer in the software stack, the fault will first cause a cluster of mapping and perception nodes to fail, and then affect the motion planning system, eventually causing the vehicle control to fail:

![crash_cam](https://github.com/user-attachments/assets/4e947a6b-48c2-4286-88c8-4e200bd0cce0)

Similarly, when we stall the GPS driver, the mapping and localization subsystems start to fail first, causing similar failures in perception, motion planning and control.
![drop_gps](https://github.com/user-attachments/assets/db1c615d-1915-4c9b-aaf3-fe2202087522)

On the other hand, users are able to inject a less severe fault in the middle of the software stack, which only causes failures to a single subsystem (mapping) without affecting downstream subsystems, due to the fact that they are somewhat resilient towards this injected fault. In this example, the failure propagation pattern can be characterized as local:
![delay_road](https://github.com/user-attachments/assets/24406b7a-a46a-4afd-931d-6408a1d62f57)

As you can see, some faults show periodic behavior, as nodes typically perform work periodically. Depending on the severity and location of where a fault is injected, it takes some time for faults to spread and the pattern is highly unpredictable by humans without domain expert knowledge. This simulator proves to be crucial to study the behavior of dynamic graph systems. Our repo contains a diverse list of faults that were injected into our example autonomous driving graph, which were used to generate training datasets. To further increase the diversity of our datasets, the graph executor is able to perform a sweep of all available faults, and inject them at different times. A dynamic graph system may respond differently depending on when a Fault is injected. Fault injection simulation at this scale is usually hard to achieve in the real world, but it is extremely feasible with our graph executor as long as users can provide corresponding configurations.

## Setup

Clone the repo with:

```bash
cd ~
git clone https://github.com/yundddd/graph_generator.git
```

Install [bazel](https://bazel.build/install) to get hermetic and reproducible builds. It works on Linux or Mac out of box. If you are on Windows, please enable [WSL](https://learn.microsoft.com/en-us/windows/wsl/install) and clone the repo inside.

## Run the generator

Execute the following command to generate an execution graph based on the defined structure:

```bash
# ensure we are at the repo root
cd ~/graph_generator
```

Dump the edge index for the graph defined by `graph.yaml` to a file:

```bash
bazel run //graph_generator:main -- --graph graph_generator/config/graph.yaml --edge_index_output ~/edge
```

Run graph executor based on graph.yaml and stop at time unit `50`, save node features to a file:

```bash
bazel run //graph_generator:main -- --graph graph_generator/config/graph.yaml --node_feature_output ~/out --stop 50
```

Run graph executor and inject a fault specified in `drop_loop.yaml`. The `--fault_label_output` must be specified to capture where and when a fault was injected. The fault_label_output file contains a single line in the form of `node_index,fault_injection_time`. The fault injection time can be specified in the fault injection yaml config, and be overridden by the `--inject_at` option. When `--viz` is used, an animation will be shown. Blue nodes are considered healthy, while red nodes are exhibiting faulty behaviors (for example, dropping, delaying callbacks/messages). One can observe how faults propagate from one node to all downstream node, and even how faults recover as time goes by.

```bash
bazel run //graph_generator:main -- --graph graph_generator/config/graph.yaml --node_feature_output ~/out --fault graph_generator/config/drop_loop.yaml --fault_label_output ~/fault_label --inject_at 30 --viz --stop 150
```

## Config Language

A graph structure can be defined using yaml file that contains node configurations. For example, the following config describes a graph involving 2 nodes A and B:

```yaml
nodes:
  - name: A
    loop:
      period: 10
      callback:
        publish:
          - topic: topic1
            value_range: [0, 10]
            delay_range: [0, 2]
nodes:
  - name: B
    subscribe:
      topic: topic1
      valid_range: [0, 10]
```

Node A periodically (every 10 time units) publishes to topic `topic1` which is subscribed by node B. The published message value falls uniformly between range [0, 10] and node B will receive the message after a short delay (between [0, 2] to model message passing delay).

Upon receiving the message from node A, node B will perform input checking against it's own valid_range, and act accordingly, for example, execute callbacks for report bad inputs on a different topic. Please see [node.py](graph_generator/node.py) for a complete set of configuration that defines a node.

Faults can be defined in the following way:

```yaml
inject_to: B
inject_at: 20
affect_receive:
  topic: topic1
  delay: 3
```

This config injects a fault to node B at time 20 to delay its receipt of messages on `topic1`. Please see this [fault_injection.py](graph_generator/fault_injection.py) for a full list of faults supported.

## Example Configs

In the [config](graph_generator/config/autonomous_vehicle/) folder, we have created an example graph that approximates autonomous vehicle software architecture. You can visualize how faults propagate with the following command:

```bash
bazel run //graph_generator:main -- --graph graph_generator/config/autonomous_vehicle/graph.yaml --node_feature_output ~/out --fault graph_generator/config/autonomous_vehicle/faults/crash_camera_driver1.yaml --fault_label_output /tmp/a --stop 200 --inject_at 10 --viz
```

> ⚠️ **Warning**:: Using `--viz` can slow down execution significantly therefore when this flag is present, dataset generation is turned of.

## Generating Datasets

The executor is capable of generating a large number of datasets based on configurations. Users can sweep over define faults and inject them at various time. For example, by running the following command:

```bash
bazel run //graph_generator/dataset:generate_datasets -- --graph graph_generator/config/autonomous_vehicle/graph.yaml --output_dir ~/output  --fault_dir graph_generator/config/autonomous_vehicle/faults --stop 1500 --fault_begin 800 --fault_end 1100 --max_num_sweep 30
```

the executor injects all faults specified in the fault_dir directory into the graph (defined by graph.yaml), and sweeps the injection time between 800 and 1100 time units with equal partitions (800,810,820...). Sweeping the fault injection time may allow models to learn fault transition better. The output files have the following structure:

```
- ~/output/
   |_____ fault_file1_name/
          |______ edge_index.csv
          |______ fault_label_inject_at_800.csv
          |______ fatul_label_inject_at_810.csv
          ...
          |______ node_feature_inject_at_800.csv
          |______ node_feature_inject_at_800.csv
          ...

   |_____ fault_file2_name/
          |______ edge_index.csv
          |______ fault_label_inject_at_800.csv
          |______ fatul_label_inject_at_810.csv
          ...
          |______ node_feature_inject_at_800.csv
          |______ node_feature_inject_at_800.csv
          ...
   |_____ fault_file3_name/
          |______ edge_index.csv
          |______ fault_label_inject_at_800.csv
          |______ fatul_label_inject_at_810.csv
          ...
          |______ node_feature_inject_at_800.csv
          |______ node_feature_inject_at_800.csv
          ...
    ...
```

> **Note**: It is intended to always output the edge_index even though we are running the command with the same graph over and over again, in order to make dataset conversion easier (by treating the entire sub-fault directory as input).

## Limitation

This graph executor is designed to be able to model any kind of graph with pub-sub relationships. But there are some limitations in implementation that users should be aware of.

Each topic can only have a single publisher. This limitation can be seen in real world when people want to reduce implementation complexity as it typically involves solving race condition amongst multiple publishers. However, multi-publisher topics can be approximated by using multiple topics with single publishers.

This executor does not model time spent on completing work and assumes it takes 0 time to finish all callbacks. This unfortunately doesn't allow us to model nodes getting stuck and not able to produce meaningful outputs. However, we might support it in the future.

## Lint

Remember to apply lint before submitting PRs. The max line length for this repo is 88.

```bash
# At project root
./lint.sh
```

## Running notebooks

Jupyter notebooks in `notebooks` directory can be run with:

```bash
bazel run //notebooks:gnn
```

A Jupyter notebook server will be started and print out the server address:

```bash
[I 21:27:13.442 NotebookApp] Jupyter Notebook 6.5.7 is running at:
[I 21:27:13.442 NotebookApp] http://localhost:8888/?token=3d162666a16919836d2e93242300777e395c086e2390f729
```

A browser will also open that allows you to experiment. However, sometimes code change in browser will not be saved to the source notebook. A more reliable way is to use VS-code's Jupyter plugin and edit right inside the editor. Copy and paste the Jupyter notebook server address when selecting the kernel.

<img src="selecting_kernel.png" alt="Graph Executor" width="700"/>
