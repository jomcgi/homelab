"""Smoke tests for tools/cli/main.py."""

import pytest
from typer.testing import CliRunner

from tools.cli.main import app


class TestMainHelp:
    def test_help_exits_zero(self):
        """Top-level --help returns exit code 0 and shows the app description."""
        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Token-efficient" in result.output

    def test_knowledge_subcommand_help_exits_zero(self):
        """knowledge --help returns exit code 0 without real auth."""
        runner = CliRunner()
        result = runner.invoke(app, ["knowledge", "--help"])
        assert result.exit_code == 0
        assert "search" in result.output
        assert "note" in result.output
