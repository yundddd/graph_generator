load("@pip//:requirements.bzl", "requirement")
load("//tools/rules/python:defs.bzl", "graph_generator_py_binary")

graph_generator_py_binary(
    name = "isort",
    srcs = ["main.py"],
    main = "main.py",
    deps = [
        requirement("isort"),
    ],
)
