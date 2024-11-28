load("@pip//:requirements.bzl", "requirement")
load("//notebooks:notebook.bzl", "notebook")

notebook(
    name = "gnn",
    srcs = ["GNN_models.ipynb"],
    deps = [
        requirement("torch"),
        requirement("torch-geometric"),
        requirement("matplotlib"),
        requirement("scikit-learn"),
        requirement("seaborn"),
        requirement("wandb"),
    ],
)
