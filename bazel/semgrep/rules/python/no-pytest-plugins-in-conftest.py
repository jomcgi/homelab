# Tests for no-pytest-plugins-in-conftest rule.

# ruleid: no-pytest-plugins-in-conftest
pytest_plugins = ["my_plugin"]

# ruleid: no-pytest-plugins-in-conftest
pytest_plugins = "my_plugin"

# ruleid: no-pytest-plugins-in-conftest
pytest_plugins = [
    "my_plugin",
    "another_plugin",
]

# ok: no-pytest-plugins-in-conftest
plugins = ["my_plugin"]

# ok: no-pytest-plugins-in-conftest
some_plugins = ["my_plugin"]
