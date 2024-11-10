load("@pip//:requirements.bzl", "requirement")
load("//tools/rules/python:defs.bzl", "graph_generator_py_library")

exports_files(["main.py"])

graph_generator_py_library(
    name = "main",
    srcs = ["main.py"],
    visibility = ["//visibility:public"],
    deps = [
        requirement("notebook"),
    ],
)
