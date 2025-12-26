load("@rules_uv//uv:pip.bzl", "pip_compile")

pip_compile(
    name = "runtime",
    requirements_in = "//:pyproject.toml",
    requirements_txt = "runtime.txt",
    tags = ["no-remote"],  # Requires internet access, skip on remote executors
    universal = True,  # Generate cross-platform lock file (macOS + Linux)
)

pip_compile(
    name = "requirements.all",
    data = glob([
        "*.in",
        "*.txt",
    ]),
    requirements_in = "all.in",
    requirements_txt = "all.txt",
    tags = ["no-remote"],  # Requires internet access, skip on remote executors
    universal = True,  # Generate cross-platform lock file (macOS + Linux)
)
