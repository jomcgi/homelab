"""Architectural enforcement tests for the modular monolith.

These tests verify that domain modules follow the modularity conventions
required by the register-based architecture. They are intentionally strict:
any violation should be fixed in the domain code, not by relaxing the tests.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import sys
from pathlib import Path

import pytest
from fastapi import APIRouter

_MONOLITH_ROOT = Path(__file__).resolve().parent.parent
_DOMAINS = ["home", "chat", "knowledge"]
_ALLOWED_CROSS_IMPORTS = {"shared", "app"}


# ---------------------------------------------------------------------------
# 1. Domain registration
# ---------------------------------------------------------------------------


class TestDomainRegistration:
    """Every domain must expose a ``register(app)`` function in its __init__.py."""

    @pytest.mark.parametrize("domain", _DOMAINS)
    def test_register_function_exists(self, domain: str) -> None:
        mod = importlib.import_module(domain)
        assert hasattr(mod, "register"), (
            f"{domain}/__init__.py must expose a register(app) function"
        )

    @pytest.mark.parametrize("domain", _DOMAINS)
    def test_register_accepts_app_argument(self, domain: str) -> None:
        mod = importlib.import_module(domain)
        register = getattr(mod, "register", None)
        assert register is not None, f"{domain} has no register function"

        sig = inspect.signature(register)
        params = [
            p for p in sig.parameters.values() if p.default is inspect.Parameter.empty
        ]
        assert len(params) >= 1, (
            f"{domain}.register() must accept at least one positional argument (app)"
        )


# ---------------------------------------------------------------------------
# 2. Import boundaries
# ---------------------------------------------------------------------------


def _collect_imports(source: str) -> list[str]:
    """Return all top-level imported module names from *source* using AST parsing."""
    tree = ast.parse(source)
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.append(node.module)
    return modules


def _top_level_package(module_name: str) -> str:
    return module_name.split(".")[0]


def _is_cross_domain_submodule_import(module_name: str, own_domain: str) -> bool:
    """Return True if *module_name* reaches into another domain's sub-modules.

    Allowed:
      - Importing own domain (``own_domain`` or ``own_domain.sub``)
      - Importing from ``shared``, ``app``, or stdlib/third-party
      - Importing another domain's top-level package (e.g. ``knowledge``)

    Forbidden:
      - Importing another domain's sub-module (e.g. ``knowledge.store``)
    """
    top = _top_level_package(module_name)

    # Own domain is always fine
    if top == own_domain:
        return False

    # Shared / app layer is always fine
    if top in _ALLOWED_CROSS_IMPORTS:
        return False

    # If the top-level is another domain, a dotted import is forbidden
    if top in _DOMAINS and "." in module_name:
        return True

    return False


class TestImportBoundaries:
    """Domain modules must not reach into other domains' sub-modules."""

    @pytest.mark.parametrize("domain", _DOMAINS)
    def test_no_cross_domain_submodule_imports(self, domain: str) -> None:
        domain_dir = _MONOLITH_ROOT / domain
        if not domain_dir.is_dir():
            pytest.fail(f"Domain directory {domain_dir} does not exist")

        violations: list[str] = []
        for py_file in sorted(domain_dir.rglob("*.py")):
            # Test files can import whatever they need
            if py_file.name.endswith("_test.py"):
                continue

            rel = py_file.relative_to(_MONOLITH_ROOT)
            source = py_file.read_text()
            for mod in _collect_imports(source):
                if _is_cross_domain_submodule_import(mod, domain):
                    violations.append(f"  {rel}: imports {mod}")

        assert not violations, (
            f"Cross-domain sub-module imports found in {domain}/:\n"
            + "\n".join(violations)
        )


# ---------------------------------------------------------------------------
# 3. Route prefix convention
# ---------------------------------------------------------------------------


class TestRoutePrefixConvention:
    """Every APIRouter in a domain must use ``/api/{{domain_name}}`` as its prefix."""

    @pytest.mark.parametrize("domain", _DOMAINS)
    def test_router_prefixes(self, domain: str) -> None:
        domain_dir = _MONOLITH_ROOT / domain
        if not domain_dir.is_dir():
            pytest.fail(f"Domain directory {domain_dir} does not exist")

        expected_prefix = f"/api/{domain}"
        violations: list[str] = []

        for py_file in sorted(domain_dir.rglob("*.py")):
            # Skip test files and __init__.py
            if py_file.name.endswith("_test.py") or py_file.name == "__init__.py":
                continue

            module_path = (
                str(py_file.relative_to(_MONOLITH_ROOT))
                .replace("/", ".")
                .removesuffix(".py")
            )

            try:
                mod = importlib.import_module(module_path)
            except Exception:
                # Module may have side effects or unresolvable deps; skip
                continue

            for name, obj in inspect.getmembers(mod):
                if not isinstance(obj, APIRouter):
                    continue
                if not obj.prefix.startswith(expected_prefix):
                    violations.append(
                        f"  {module_path}.{name}: prefix={obj.prefix!r} "
                        f"(expected prefix starting with {expected_prefix!r})"
                    )

        assert not violations, f"Router prefix violations in {domain}/:\n" + "\n".join(
            violations
        )
