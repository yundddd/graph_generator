load("//graph_generator/config:merge_yaml.bzl", "merge_yaml")

package(default_visibility = ["//visibility:public"])

# merge multiple subsystem into a single graph.yaml, which can be consumed
# by the executor.
merge_yaml(
    name = "graph",
    srcs = [
        "control.yaml",
        "mapping.yaml",
        "motion_planning.yaml",
        "perception.yaml",
        "sensor.yaml",
    ],
    out = "graph.yaml",
)

filegroup(
    name = "config",
    srcs = glob(["faults/**/*"]) + [":graph"],
)
