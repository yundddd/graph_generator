def merge_yaml(name, srcs, out):
    """Merge multiple YAML files into a single output file."""
    native.genrule(
        name = name,
        srcs = srcs,
        outs = [out],
        cmd = "$(location //graph_generator/config:merge_yaml) $(SRCS) $@",
        tools = ["//graph_generator/config:merge_yaml"],
    )
