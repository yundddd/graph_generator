load("@pip//:requirements.bzl", "requirement")
load("//tools/rules/python:defs.bzl", "graph_generator_py_binary", "graph_generator_py_image", "graph_generator_py_library")

graph_generator_py_library(
    name = "strict_base_model",
    srcs = [
        "strict_base_model.py",
    ],
    visibility = ["//visibility:public"],
    deps = [
        requirement("pydantic"),
    ],
)

graph_generator_py_library(
    name = "node",
    srcs = [
        "node.py",
    ],
    visibility = ["//visibility:public"],
    deps = [":strict_base_model"],
)

graph_generator_py_library(
    name = "graph",
    srcs = [
        "graph.py",
        ":node",
    ],
    visibility = ["//visibility:public"],
    deps = [
        requirement("networkx"),
        requirement("matplotlib"),
        ":strict_base_model",
    ],
)

graph_generator_py_library(
    name = "fault_injection",
    srcs = [
        "fault_injection.py",
    ],
    visibility = ["//visibility:public"],
    deps = [
        ":strict_base_model",
    ],
)

graph_generator_py_library(
    name = "executor",
    srcs = [
        "executor.py",
    ],
    visibility = ["//visibility:public"],
    deps = [
        ":fault_injection",
        ":graph",
        ":node",
    ],
)

graph_generator_py_binary(
    name = "main",
    srcs = [
        "main.py",
    ],
    data = [
        "//graph_generator/config",  # all configs including merged ones
    ],
    main = "main.py",
    visibility = ["//visibility:public"],
    deps = [
        ":executor",
        ":graph",
        requirement("click"),
        requirement("PyYAML"),
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
