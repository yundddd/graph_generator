load("@rules_python//python:pip.bzl", "compile_pip_requirements")

# Set up our pip requirements
compile_pip_requirements(
    name = "requirements",
    requirements_in = "requirements.in",
    requirements_linux = "requirements_lock_linux.txt",
    requirements_darwin = "requirements_lock_darwin.txt",
    requirements_txt = "requirements_lock.txt",
)