"""Command-line interface for Context Hub foundation commands."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .project import init_project, project_status
from .scanner import scan_repository
from .graph import build_code_graph
from .storage import index_repository, IndexDatabase
from .retrieval import RetrievalEngine, RetrievalQuery
from .analysis import analyze_task
from .providers import get_provider
from .providers.config import ProviderSettings

app = typer.Typer(name="ctx", help="Context orchestration infrastructure for coding agents.")
provider_app = typer.Typer(name="provider", help="Provider configuration commands.")
app.add_typer(provider_app)
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
    index = IndexDatabase(path.resolve() / ".context-hub" / "index.db")
    try:
        index.open()
        index_data = index.status(path.resolve())
    finally:
        index.close()
    if index_data:
        console.print(f"Index: initialized | Files: {index_data['files']} | Symbols: {index_data['symbols']} | Imports: {index_data['imports']}")
        console.print(f"Last indexed: {index_data['last_indexed'] or 'never'}")
    else:
        console.print("Index: not initialized")


@app.command()
def index(path: Annotated[Path, typer.Argument(help="Project directory.")] = Path("."),
          force: Annotated[bool, typer.Option("--force", help="Reparse all discovered files.")] = False) -> None:
    """Create or incrementally update the local SQLite repository index."""
    result = index_repository(path, force=force)
    console.print("Context Hub Index")
    for label in ("scanned", "new", "modified", "deleted", "unchanged", "parsed"):
        console.print(f"{label.title()}: {getattr(result, label)}")
    console.print("[green]Index updated successfully.[/green]")


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


@app.command("graph")
def graph_command(path: Annotated[Path, typer.Argument(help="Repository directory.")] = Path(".")) -> None:
    """Build and summarize the repository code graph."""
    repository = scan_repository(path)
    graph = build_code_graph(repository)
    counts: dict[str, int] = {}
    for edge in graph.edges:
        counts[edge.kind] = counts.get(edge.kind, 0) + 1
    console.print("Context Hub Code Graph")
    for key, value in graph.stats().items():
        console.print(f"{key.replace('_', ' ').title()}: {value}")


def _graph_for_current_repo() -> tuple[object, Path]:
    root = Path.cwd()
    return build_code_graph(scan_repository(root)), root


@app.command()
def deps(path: Annotated[Path, typer.Argument(help="Repository-relative file path.")]) -> None:
    """Show direct dependencies of a file."""
    graph, _ = _graph_for_current_repo()
    node = f"file:{path.as_posix()}"
    if graph.get_node(node) is None:
        console.print(f"File not found or ignored: {path}")
        raise typer.Exit(code=1)
    console.print(f"Dependencies for {path}")
    for target in sorted(graph.get_dependencies(node)):
        item = graph.get_node(target)
        console.print(f"  → {item.path if item and item.path else item.name if item else target}")


@app.command()
def dependents(path: Annotated[Path, typer.Argument(help="Repository-relative file path.")]) -> None:
    """Show files that depend on a file."""
    graph, _ = _graph_for_current_repo()
    node = f"file:{path.as_posix()}"
    if graph.get_node(node) is None:
        console.print(f"File not found or ignored: {path}")
        raise typer.Exit(code=1)
    console.print(f"Dependents of {path}")
    for source in sorted(graph.dependents(node)):
        item = graph.get_node(source)
        console.print(f"  ← {item.path if item and item.path else source}")


@app.command("search")
def search(query: Annotated[str, typer.Argument(help="Task or search query.")],
           limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 20,
           path: Annotated[str | None, typer.Option("--path", help="Restrict results to a path prefix.")] = None,
           explain: Annotated[bool, typer.Option("--explain", help="Show score explanations.")] = False) -> None:
    """Search indexed repository context using lexical and graph signals."""
    database_path = Path.cwd() / ".context-hub" / "index.db"
    if not database_path.is_file():
        console.print("No Context Hub index found. Run `ctx index` first.")
        raise typer.Exit(code=1)
    results = RetrievalEngine(database_path).search(RetrievalQuery(task=query, max_results=limit))
    if path:
        results = [result for result in results if result.path.startswith(path)]
    console.print("Context Hub Search")
    console.print(f"Query: {query}\n")
    if not results:
        console.print("No relevant indexed context found.")
        return
    for position, result in enumerate(results, 1):
        console.print(f"{position}. {result.path}" + (f" :: {result.symbol}" if result.symbol else ""))
        console.print(f"   Score: {result.score:.2f}")
        console.print(f"   Signals: {', '.join(result.signals)}")
        console.print(f"   Reason: {'; '.join(result.reasons)}")
        console.print(f"   Estimated tokens: {result.estimated_tokens}")
        if explain:
            console.print("   Score breakdown: " + ", ".join(result.signals))


@provider_app.command("status")
def provider_status() -> None:
    """Show local provider configuration without making a network request."""
    settings = ProviderSettings.from_env()
    console.print(f"Provider: {settings.provider.title()}")
    console.print(f"Model: {settings.model}")
    console.print(f"API key: {'configured' if settings.api_key else 'missing'}")
    console.print(f"Endpoint: {settings.base_url}")


@app.command()
def analyze(task: Annotated[str, typer.Argument(help="Developer task to analyze.")],
            limit: Annotated[int, typer.Option("--limit", min=1, max=50)] = 10,
            json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Analyze a developer task with repository metadata and the configured provider."""
    try:
        result = analyze_task(task, get_provider(), Path.cwd(), limit=limit)
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    if json_output:
        console.print(result.model_dump_json(indent=2)); return
    console.print("Task Analysis")
    console.print(f"Type: {result.task_type}\nDomains: {', '.join(result.domains) or 'none'}\nKeywords: {', '.join(result.keywords) or 'none'}\nLikely Files: {', '.join(result.likely_files) or 'none'}\nLikely Symbols: {', '.join(result.likely_symbols) or 'none'}\nRequired Context: {', '.join(result.required_context) or 'none'}\nAmbiguities: {', '.join(result.ambiguities) or 'none'}\nConfidence: {result.confidence:.2f}\nReasoning: {result.reasoning}")


if __name__ == "__main__":
    app()

