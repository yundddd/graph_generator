load("@pip//:requirements.bzl", "requirement")
load("//notebooks:notebook.bzl", "notebook")

notebook(
    name = "gnn",
    srcs = ["GNN_models.ipynb"],
    deps = [
        requirement("torch"),
        requirement("torch-geometric"),
        requirement("matplotlib"),
    ],
)

notebook(
    name = "colab4",
    srcs = ["colab4.ipynb"],
    deps = [
        requirement("torch"),
        requirement("torch-geometric"),
        requirement("torch-scatter"),
        requirement("torch-sparse"),
        requirement("matplotlib"),
        requirement("pandas"),
        requirement("networkx"),
    ],
)