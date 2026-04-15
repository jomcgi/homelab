"""Tests for python_deps.py — the shim binary that packages pip deps into the tools image.

python_deps.py has no functions of its own; it is a shim that imports the
pip packages that must be present in the tools image (httpx, typer) so that
py_image_layer can discover and package their transitive dependency trees.

These tests verify that those imports are actually resolvable at test time,
which catches cases where a package is removed from the dep list or the dep
declaration drifts out of sync with what is actually needed.
"""

import importlib


def test_httpx_importable():
    """httpx is needed by the homelab CLI (tools/cli/) at runtime."""
    mod = importlib.import_module("httpx")
    assert mod is not None


def test_typer_importable():
    """typer is needed by the homelab CLI (tools/cli/main.py) at runtime."""
    mod = importlib.import_module("typer")
    assert mod is not None


def test_httpx_client_constructible():
    """Sanity-check that httpx.Client can be instantiated (not just imported)."""
    import httpx

    client = httpx.Client()
    assert client is not None
    client.close()


def test_typer_app_constructible():
    """Sanity-check that typer.Typer can be instantiated (not just imported)."""
    import typer

    app = typer.Typer()
    assert app is not None
