"""Command-line interface for Context Hub foundation commands."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .project import init_project, project_status
from .scanner import scan_repository

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


@app.command()
def scan(path: Annotated[Path, typer.Argument(help="Repository directory.")] = Path(".")) -> None:
    """Scan repository files and report deterministic intelligence."""
    repository = scan_repository(path)
    parsed = [f for f in repository.files if f.parsed is not None]
    symbols = sum(len(f.parsed.symbols) for f in parsed)
    imports = sum(len(f.parsed.imports) for f in parsed)
    console.print(f"Files: {len(repository.files)}")
    for language, count in sorted({f.language: sum(x.language == f.language for x in repository.files) for f in repository.files}.items()):
        console.print(f"  {language}: {count}")
    console.print(f"Source files parsed: {len(parsed)}")
    console.print(f"Symbols discovered: {symbols}")
    console.print(f"Imports discovered: {imports}")
    console.print("[green]✓ Repository scan complete[/green]")


def _file_or_exit(root: Path, relative: Path):
    repository = scan_repository(root)
    target = relative.as_posix()
    for item in repository.files:
        if item.path == target:
            return item
    console.print(f"File not found or ignored: {target}")
    raise typer.Exit(code=1)


@app.command()
def inspect(path: Annotated[Path, typer.Argument(help="Repository-relative file path.")]) -> None:
    """Inspect one repository file."""
    item = _file_or_exit(Path.cwd(), path)
    console.print(item.path)
    console.print(f"Language: {item.language}\nLines: {item.lines}\nSize: {item.size} bytes")
    if item.parsed:
        console.print(f"Symbols: {len(item.parsed.symbols)}\nImports: {len(item.parsed.imports)}")
        for symbol in item.parsed.symbols:
            console.print(f"  {symbol.kind.value} {symbol.name} (line {symbol.start_line})")
        for imported in item.parsed.imports:
            console.print(f"  import {imported.name} (line {imported.line})")
    if item.parsed and item.parsed.parse_error:
        console.print(f"Parse warning: {item.parsed.parse_error}")


@app.command()
def symbols(path: Annotated[Path, typer.Argument(help="Repository-relative file path.")]) -> None:
    """List symbols discovered in one file."""
    item = _file_or_exit(Path.cwd(), path)
    if not item.parsed:
        console.print("No parser available for this language.")
        return
    for symbol in item.parsed.symbols:
        parent = f" ({symbol.parent})" if symbol.parent else ""
        console.print(f"{symbol.kind.value:<10} {symbol.name}{parent}  lines {symbol.start_line}-{symbol.end_line}")


if __name__ == "__main__":
    app()

