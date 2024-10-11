load("@pip//:requirements.bzl", "requirement")
load("//tools/rules/python:defs.bzl", "graph_generator_py_binary", "graph_generator_py_image", "graph_generator_py_library")

# gazelle:prefix github.com/example/graph_generator
graph_generator_py_library(
    name = "node",
    srcs = [
        "node.py",
    ],
    visibility = ["//visibility:public"],
    deps = [requirement("PyYAML")],
)

graph_generator_py_library(
    name = "graph",
    srcs = [
        "graph.py",
    ],
    visibility = ["//visibility:public"],
    deps = [
        requirement("networkx"),
        requirement("matplotlib"),
    ],
)

graph_generator_py_library(
    name = "fault_injection",
    srcs = [
        "fault_injection.py",
    ],
    visibility = ["//visibility:public"],
)

graph_generator_py_library(
    name = "executor",
    srcs = [
        "executor.py",
    ],
    visibility = ["//visibility:public"],
    deps = [
        ":graph",
        ":node",
        ":fault_injection",
    ],
)

graph_generator_py_binary(
    name = "main",
    srcs = [
        "main.py",
    ],
    main = "main.py",
    visibility = ["//visibility:public"],
    deps = [
        ":executor",
        ":graph",
        ":node",
    ],
)

# Build and run this image with
#     bazel run //graph_generator:graph_generator_img_load_docker
#     docker run --rm graph_generator:latest
graph_generator_py_image(
    name = "graph_generator_img",
    binary = ":graph_generator",
    image_tags = ["graph_generator:latest"],
)