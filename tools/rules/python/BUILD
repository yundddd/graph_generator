load("@pip//:requirements.bzl", "requirement")
load("//tools/rules/python:defs.bzl", "graph_generator_py_library")

graph_generator_py_library(
    name = "test_runner",
    srcs = ["test_runner.py"],
    visibility = ["//visibility:public"],
    deps = [
        requirement("pytest"),
    ],
)
