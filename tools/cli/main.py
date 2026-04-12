"""Homelab CLI — token-efficient cluster tooling for Claude Code."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="homelab",
    help="Token-efficient CLI for homelab operations.",
    no_args_is_help=True,
)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
