"""Click CLI entrypoint for SmartRx Safety Agents."""

from __future__ import annotations

import click

from smartrx_safety_agents.config import get_settings


@click.group()
def main() -> None:
    """SmartRx Guard clinical medication reconciliation CLI."""


@main.command()
def status() -> None:
    """Print active non-secret runtime configuration status."""
    settings = get_settings()
    click.echo(
        f"smartrx-safety-agents env={settings.environment} "
        f"model={settings.gemini_model_name} port={settings.smartrx_port}"
    )


if __name__ == "__main__":
    main()
