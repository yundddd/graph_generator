load("@pip//:requirements.bzl", "requirement")
load("@rules_python//python:defs.bzl", "py_binary")

py_binary(
    name = "merge_yaml",
    srcs = ["merge_yaml.py"],
    visibility = ["//visibility:public"],
    deps = [
        requirement("click"),
        requirement("PyYAML"),
    ],
)

filegroup(
    name = "config",
    srcs = glob(["**/*"]) + [
        "//graph_generator/config/autonomous_vehicle:config",
    ],
    visibility = ["//visibility:public"],
)
