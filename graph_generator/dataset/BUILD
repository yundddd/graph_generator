load("@pip//:requirements.bzl", "requirement")
load("//tools/rules/python:defs.bzl", "graph_generator_py_binary")

graph_generator_py_binary(
    name = "generate_datasets",
    srcs = [
        "generate_datasets.py",
    ],
    data = [
        "//graph_generator/config",  # all configs including merged ones
    ],
    main = "generate_datasets.py",
    visibility = ["//visibility:public"],
    deps = [
        "//graph_generator:main",
        requirement("click"),
    ],
)
