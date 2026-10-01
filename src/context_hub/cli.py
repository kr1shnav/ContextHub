"""Command-line interface for Context Hub foundation commands."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .project import init_project, project_status

app = typer.Typer(name="ctx", help="Context orchestration infrastructure for coding agents.")
console = Console()


@app.command()
def version() -> None:
    """Print the Context Hub version."""
    console.print(f"Context Hub {__version__}")


@app.command()
def init(path: Annotated[Path, typer.Argument(help="Project directory.")] = Path(".")) -> None:
    """Initialize Context Hub metadata for a project."""
    directory, has_git = init_project(path)
    console.print(f"[green]Initialized[/green] {directory}")
    if has_git:
        console.print("Git repository detected.")
    else:
        console.print("[yellow]No Git repository detected.[/yellow] Initialize Git when ready.")


@app.command()
def status(path: Annotated[Path, typer.Argument(help="Project directory.")] = Path(".")) -> None:
    """Show Context Hub project status."""
    data = project_status(path.resolve())
    if data is None:
        console.print("Context Hub is not initialized. Run [bold]ctx init[/bold].")
        raise typer.Exit(code=1)
    table = Table(title="Context Hub status")
    table.add_column("Property", style="cyan")
    table.add_column("Value")
    for key in ("project_root", "git_root", "context_hub_version", "initialized_at"):
        table.add_row(key, str(data.get(key) or "not detected"))
    console.print(table)


if __name__ == "__main__":
    app()

