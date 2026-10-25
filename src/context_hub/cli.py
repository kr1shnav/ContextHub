"""Command-line interface for Context Hub foundation commands."""

import json
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
from .providers import MockProvider, get_provider
from .providers.config import ProviderSettings
from .orchestration import ContextBudget, ContextOrchestrator
from .mcp_server import serve_stdio
from .agent_harness import AgentHarness, AgentTask
from .proposals import ProposalGenerator, ProposalLimits
from .proposals import ChangeProposal, ProposedFileDiff
from .validation import CheckKind, ProposalValidator, ValidationCheck, ValidationRequest
from .benchmark import load_dataset, summarize, verify_expected_evidence
from .evaluation import evaluate_dataset, index_metadata, render_summary
from .packet_evaluation import evaluate_packets, render_packet_summary
from .performance import run_performance_benchmark, render_performance_summary, validate_repeats
from .agent_evaluation import AgentTaskDataset, evaluate_agent_dataset, render_agent_summary
from .unified_evaluation import SUITES, run_unified_evaluation, render_unified_summary

app = typer.Typer(name="ctx", help="Context orchestration infrastructure for coding agents.")
provider_app = typer.Typer(name="provider", help="Provider configuration commands.")
mcp_app = typer.Typer(name="mcp", help="Model Context Protocol server commands.")
agent_app = typer.Typer(name="agent", help="Read-only agent planning and proposal commands.")
eval_app = typer.Typer(name="eval", help="Deterministic benchmark evaluation commands.")
app.add_typer(provider_app)
app.add_typer(mcp_app)
app.add_typer(agent_app)
app.add_typer(eval_app)
console = Console()


@mcp_app.command("serve")
def mcp_serve() -> None:
    """Start the Context Hub MCP server over stdio."""
    try:
        serve_stdio()
    except Exception as exc:
        typer.echo(f"Context Hub MCP server failed to start: {exc}", err=True)
        raise typer.Exit(code=1) from exc


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


@app.command("benchmark-validate")
def benchmark_validate(dataset: Annotated[Path | None, typer.Option("--dataset", help="Benchmark JSON path.")] = None,
                       repository: Annotated[Path, typer.Option("--repository", help="Repository to verify expected evidence against.")] = Path(".")) -> None:
    """Validate and summarize the offline retrieval benchmark dataset."""
    try:
        loaded = load_dataset(dataset)
        errors = verify_expected_evidence(loaded, repository)
    except Exception as exc:
        console.print(f"[red]Benchmark validation failed: {exc}[/red]")
        raise typer.Exit(code=1) from exc
    data = summarize(loaded)
    console.print(f"Benchmark: {data['name']} (v{data['version']})")
    console.print(f"Tasks: {data['tasks']} | Ambiguous: {data['ambiguous']}")
    if errors:
        for error in errors:
            console.print(f"[red]Error: {error}[/red]")
        raise typer.Exit(code=1)
    console.print("[green]Dataset and expected repository evidence are valid.[/green]")


@eval_app.command("retrieval")
def eval_retrieval(k: Annotated[list[int], typer.Option("--k", min=1, help="Positive cutoff; repeat for multiple K values.")] = [1, 3, 5],
                   json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
                   output: Annotated[Path | None, typer.Option("--output", help="Write JSON results to this file.")] = None,
                   dataset: Annotated[Path | None, typer.Option("--dataset", help="Benchmark JSON path.")] = None) -> None:
    """Evaluate retrieval against the offline benchmark dataset."""
    root = Path.cwd()
    database_path = root / ".context-hub" / "index.db"
    if not database_path.is_file():
        console.print("No Context Hub index found. Run `ctx index` first.")
        raise typer.Exit(code=1)
    try:
        loaded = load_dataset(dataset)
        errors = verify_expected_evidence(loaded, root)
        if errors:
            raise ValueError("; ".join(errors))
        report = evaluate_dataset(loaded, RetrievalEngine(database_path), k, index_metadata=index_metadata(database_path, root))
        if output:
            output.write_text(report.to_json() + "\n", encoding="utf-8")
    except Exception as exc:
        console.print(f"[red]Retrieval evaluation failed: {exc}[/red]")
        raise typer.Exit(code=1) from exc
    if json_output:
        console.print(report.to_json())
    else:
        console.print(render_summary(report))
        if output:
            console.print(f"JSON results: {output}")


@eval_app.command("packets")
def eval_packets(max_files: Annotated[int, typer.Option("--max-files", min=1, max=100)] = 10,
                 max_tokens: Annotated[int, typer.Option("--max-tokens", min=1)] = 6000,
                 max_characters: Annotated[int, typer.Option("--max-characters", min=1)] = 24000,
                 json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
                 output: Annotated[Path | None, typer.Option("--output", help="Write JSON results to this file.")] = None,
                 dataset: Annotated[Path | None, typer.Option("--dataset", help="Benchmark JSON path.")] = None) -> None:
    """Evaluate actual context packets against the offline benchmark dataset."""
    root = Path.cwd()
    database_path = root / ".context-hub" / "index.db"
    if not database_path.is_file():
        console.print("No Context Hub index found. Run `ctx index` first.")
        raise typer.Exit(code=1)
    try:
        loaded = load_dataset(dataset)
        errors = verify_expected_evidence(loaded, root)
        if errors:
            raise ValueError("; ".join(errors))
        budget = ContextBudget(max_files=max_files, max_tokens=max_tokens, max_characters=max_characters)
        builder = ContextOrchestrator(root, MockProvider(), budget=budget)
        report = evaluate_packets(loaded, builder, budget, index_metadata=index_metadata(database_path, root))
        if output:
            output.write_text(report.to_json() + "\n", encoding="utf-8")
    except Exception as exc:
        console.print(f"[red]Packet evaluation failed: {exc}[/red]")
        raise typer.Exit(code=1) from exc
    if json_output:
        console.print(report.to_json())
    else:
        console.print(render_packet_summary(report))
        if output:
            console.print(f"JSON results: {output}")


@eval_app.command("performance")
def eval_performance(repository: Annotated[Path, typer.Option("--repository", help="Repository to copy into isolated benchmark fixtures.")] = Path("."),
                     repeats: Annotated[int, typer.Option("--repeats", min=1, max=100)] = 3,
                     warmups: Annotated[int, typer.Option("--warmups", min=0, max=20)] = 1,
                     max_files: Annotated[int, typer.Option("--max-files", min=1, max=100)] = 10,
                     max_tokens: Annotated[int, typer.Option("--max-tokens", min=1)] = 6000,
                     max_characters: Annotated[int, typer.Option("--max-characters", min=1)] = 24000,
                     json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
                     output: Annotated[Path | None, typer.Option("--output", help="Write JSON results to this file.")] = None,
                     dataset: Annotated[Path | None, typer.Option("--dataset", help="Benchmark JSON path.")] = None) -> None:
    """Measure isolated indexing, retrieval, packet, and incremental performance."""
    try:
        validate_repeats(repeats, warmups)
        source = repository.resolve()
        if not source.is_dir():
            raise ValueError(f"repository does not exist: {source}")
        loaded = load_dataset(dataset)
        errors = verify_expected_evidence(loaded, source)
        if errors:
            raise ValueError("; ".join(errors))
        report = run_performance_benchmark(source, loaded, repeats=repeats, warmups=warmups,
            budget=ContextBudget(max_files=max_files, max_tokens=max_tokens, max_characters=max_characters))
        if output:
            output.write_text(report.to_json() + "\n", encoding="utf-8")
    except Exception as exc:
        console.print(f"[red]Performance benchmark failed: {exc}[/red]")
        raise typer.Exit(code=1) from exc
    if json_output:
        console.print(report.to_json())
    else:
        console.print(render_performance_summary(report))
        if output:
            console.print(f"JSON results: {output}")


@eval_app.command("agent")
def eval_agent(repository: Annotated[Path, typer.Option("--repository", help="Repository used for objective path and symbol checks.")] = Path("."),
               artifacts: Annotated[Path | None, typer.Option("--artifacts", help="JSON artifact bundle keyed by agent task ID.")] = None,
               json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
               output: Annotated[Path | None, typer.Option("--output", help="Write JSON results to this file.")] = None,
               dataset: Annotated[Path | None, typer.Option("--dataset", help="Agent benchmark JSON path.")] = None) -> None:
    """Evaluate offline agent plans, proposals, and validation reports."""
    try:
        root = repository.resolve()
        if not root.is_dir():
            raise ValueError(f"repository does not exist: {root}")
        loaded = AgentTaskDataset.load(dataset or Path(__file__).with_name("data") / "agent_benchmark_v1.json")
        artifact_data = json.loads(artifacts.read_text(encoding="utf-8")) if artifacts else {}
        if not isinstance(artifact_data, dict):
            raise ValueError("artifact bundle must be a JSON object keyed by task ID")
        report = evaluate_agent_dataset(loaded, root, artifacts=artifact_data)
        if output:
            output.write_text(report.to_json() + "\n", encoding="utf-8")
    except Exception as exc:
        console.print(f"[red]Agent evaluation failed: {exc}[/red]")
        raise typer.Exit(code=1) from exc
    if json_output:
        console.print(report.to_json())
    else:
        console.print(render_agent_summary(report))
        if output:
            console.print(f"JSON results: {output}")


@eval_app.command("all")
def eval_all(repository: Annotated[Path, typer.Option("--repository", help="Repository to evaluate.")] = Path("."),
             suite: Annotated[list[str], typer.Option("--suite", help="Suite to run; repeat to select several.")] = list(SUITES),
             baseline: Annotated[Path | None, typer.Option("--baseline", help="Previously saved unified JSON report.")] = None,
             save_baseline: Annotated[Path | None, typer.Option("--save-baseline", help="Save this unified report as a baseline.")] = None,
             k: Annotated[list[int], typer.Option("--k", min=1, help="Retrieval cutoff; repeat for multiple K values.")] = [1, 3, 5],
             repeats: Annotated[int, typer.Option("--repeats", min=1, max=100)] = 3,
             warmups: Annotated[int, typer.Option("--warmups", min=0, max=20)] = 1,
             max_files: Annotated[int, typer.Option("--max-files", min=1, max=100)] = 10,
             max_tokens: Annotated[int, typer.Option("--max-tokens", min=1)] = 6000,
             min_retrieval_precision: Annotated[float | None, typer.Option("--min-retrieval-precision", min=0, max=1)] = None,
             min_packet_coverage: Annotated[float | None, typer.Option("--min-packet-coverage", min=0, max=1)] = None,
             max_budget_violation_rate: Annotated[float | None, typer.Option("--max-budget-violation-rate", min=0, max=1)] = None,
             max_latency_regression: Annotated[float | None, typer.Option("--max-latency-regression", min=0)] = None,
             json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
             output: Annotated[Path | None, typer.Option("--output", help="Write JSON report to this file.")] = None) -> None:
    """Run selected offline evaluation suites and optional regression gates."""
    try:
        gates = {key: value for key, value in {"min_retrieval_precision": min_retrieval_precision, "min_packet_coverage": min_packet_coverage, "max_budget_violation_rate": max_budget_violation_rate, "max_latency_regression": max_latency_regression}.items() if value is not None}
        report = run_unified_evaluation(repository, suites=suite, baseline=baseline, repeats=repeats, warmups=warmups, ks=k,
            budget=ContextBudget(max_files=max_files, max_tokens=max_tokens), gates=gates)
        if save_baseline:
            save_baseline.write_text(report.to_json() + "\n", encoding="utf-8")
        if output:
            output.write_text(report.to_json() + "\n", encoding="utf-8")
    except Exception as exc:
        console.print(f"[red]Unified evaluation failed: {exc}[/red]")
        raise typer.Exit(code=1) from exc
    if json_output: console.print(report.to_json())
    else: console.print(render_unified_summary(report))
    if report.quality_gate_failures or report.failures or report.blocked:
        raise typer.Exit(code=1)


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
        settings = ProviderSettings.from_env()
        result = analyze_task(task, get_provider(settings), Path.cwd(), settings=settings, limit=limit)
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    if json_output:
        console.print(result.model_dump_json(indent=2)); return
    console.print("Task Analysis")
    console.print(f"Type: {result.task_type}\nDomains: {', '.join(result.domains) or 'none'}\nKeywords: {', '.join(result.keywords) or 'none'}\nLikely Files: {', '.join(result.likely_files) or 'none'}\nLikely Symbols: {', '.join(result.likely_symbols) or 'none'}\nRequired Context: {', '.join(result.required_context) or 'none'}\nAmbiguities: {', '.join(result.ambiguities) or 'none'}\nConfidence: {result.confidence:.2f}\nReasoning: {result.reasoning}")


@app.command("pack")
def pack(task: Annotated[str, typer.Argument(help="Developer task for context assembly.")],
         max_files: Annotated[int, typer.Option("--max-files", min=1, max=100)] = 10,
         max_tokens: Annotated[int, typer.Option("--max-tokens", min=100)] = 6000,
         no_llm: Annotated[bool, typer.Option("--no-llm", help="Use deterministic local analysis without an API provider.")] = False,
         json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Assemble a bounded, evidence-backed context packet."""
    try:
        settings = ProviderSettings.from_env()
        provider = MockProvider() if no_llm else get_provider(settings)
        packet = ContextOrchestrator(Path.cwd(), provider, settings=settings, budget=ContextBudget(max_files=max_files, max_tokens=max_tokens)).build(task)
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    if json_output:
        console.print(packet.model_dump_json(indent=2)); return
    console.print("Context Packet")
    console.print(f"Task: {packet.task}\nFiles: {packet.statistics.files_selected}\nEstimated tokens: {packet.statistics.estimated_tokens}")
    for item in packet.files:
        console.print(f"  {item.path} ({item.score:.2f}) — {item.reason}")


@agent_app.command("propose")
def agent_propose(task: Annotated[str, typer.Argument(help="Coding task for a reviewable patch proposal.")],
               max_files: Annotated[int, typer.Option("--max-files", min=1, max=100)] = 10,
               max_tokens: Annotated[int, typer.Option("--max-tokens", min=100, max=100000)] = 6000,
               output_dir: Annotated[Path | None, typer.Option("--output-dir", help="Safe directory inside the repository for the patch artifact.")] = None,
               filename: Annotated[str, typer.Option("--filename")] = "proposal.patch",
               json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Generate a validated patch proposal without applying it."""
    try:
        root = Path.cwd(); provider = get_provider(); agent_task = AgentTask(task=task, max_files=max_files, max_tokens=max_tokens)
        generator = ProposalGenerator(root, provider, limits=ProposalLimits(max_files=max_files))
        proposal = generator.generate(agent_task)
        saved = generator.save(proposal, output_dir or (root / ".context-hub" / "proposals"), filename) if output_dir else None
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    if json_output:
        console.print(proposal.model_dump_json(indent=2))
    else:
        console.print("Change Proposal")
        console.print(f"Summary: {proposal.summary}\nRationale: {proposal.rationale}")
        console.print("Files: " + ", ".join(item.path for item in proposal.files))
        if proposal.validation_recommendations: console.print("Validation recommendations: " + "; ".join(proposal.validation_recommendations))
    if saved: console.print(f"Saved proposal artifact: {saved}")


@agent_app.command("validate")
def agent_validate(proposal_file: Annotated[Path, typer.Argument(help="Saved unified-diff proposal file.")],
                   execute: Annotated[bool, typer.Option("--execute", help="Explicitly opt in to approved checks.")] = False,
                   check: Annotated[list[CheckKind] | None, typer.Option("--check", help="Approved check: pytest or py_compile.")] = None,
                   path: Annotated[str | None, typer.Option("--path", help="Repository-relative Python path for py_compile.")] = None,
                   json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Validate a saved proposal; checks are structural unless --execute is supplied."""
    try:
        root = Path.cwd(); artifact = proposal_file.resolve()
        if not artifact.is_file() or not artifact.is_relative_to(root): raise ValueError("proposal file must be inside the repository")
        text = artifact.read_text(encoding="utf-8")
        chunks = [chunk.strip() for chunk in text.split("\n\n--- ") if chunk.strip()]
        files = []
        for chunk in chunks:
            patch_text = chunk if chunk.startswith("--- ") else "--- " + chunk
            header = patch_text.splitlines()[0][4:].split("\t")[0].removeprefix("a/")
            files.append(ProposedFileDiff(path=header, patch=patch_text))
        proposal = ChangeProposal(summary="Saved proposal", rationale="Validation of saved unified diff", files=files)
        checks = [ValidationCheck(kind=item, path=path) for item in (check or [])]
        report = ProposalValidator(root).validate(proposal, ValidationRequest(checks=checks, execute=execute))
    except Exception as exc:
        console.print(f"[red]{exc}[/red]"); raise typer.Exit(code=1) from exc
    if json_output:
        console.print(report.model_dump_json(indent=2)); return
    console.print(f"Validation: {report.status.value} ({report.proposal_id})")
    for item in report.static_validation: console.print(f"  Static: {item}")
    for item in report.checks: console.print(f"  {item.kind.value}: {item.status.value}" + (f" (exit {item.exit_code})" if item.exit_code is not None else ""))
    if report.failure_output: console.print(report.failure_output)


@app.command("agent-plan")
def agent_plan(task: Annotated[str, typer.Argument(help="Coding task to turn into a repository-aware plan.")],
               max_files: Annotated[int, typer.Option("--max-files", min=1, max=100)] = 10,
               max_tokens: Annotated[int, typer.Option("--max-tokens", min=100, max=100000)] = 6000,
               json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Create a validated, read-only implementation plan from repository context."""
    try:
        plan = AgentHarness(Path.cwd(), get_provider()).plan_repository_task(AgentTask(task=task, max_files=max_files, max_tokens=max_tokens))
    except Exception as exc:
        console.print(f"[red]{exc}[/red]"); raise typer.Exit(code=1) from exc
    if json_output: console.print(plan.model_dump_json(indent=2)); return
    console.print("Repository-Aware Agent Plan")
    console.print(f"Summary: {plan.summary}\nObjective: {plan.objective}")
    for step in plan.steps: console.print(f"{step.id}: {step.description}")


if __name__ == "__main__":
    app()

