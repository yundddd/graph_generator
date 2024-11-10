load("@pip//:requirements.bzl", "requirement")
load("//tools/rules/python:defs.bzl", "graph_generator_py_binary")

def notebook(name, srcs, deps, **kwargs):
    if len(srcs) != 1:
        fail("Can only run a single notebook")
    graph_generator_py_binary(
        name = name,
        srcs = srcs + ["//tools/jupyter:main.py"],
        main = "tools/jupyter/main.py",
        deps = deps + [
            requirement("notebook"),
        ],
        **kwargs
    )
