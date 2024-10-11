load("@pip//:requirements.bzl", "requirement")
load("//tools/rules/python:defs.bzl", "graph_generator_py_binary")

graph_generator_py_binary(
    name = "ipython",
    srcs = ["main.py"],
    main = "main.py",
    deps = [
        # Include the main graph_generator binary so we can call things within it
        "//graph_generator",
        requirement("ipdb"),
    ],
)
