# Context Hub architecture

## Phase 9.2 repository-aware task planning

`AgentHarness.plan_repository_task()` converts a non-empty coding task and the
existing `ContextOrchestrator` `ContextPacket` into a bounded `RepositoryPlan`.
The plan contains an objective, ordered steps, supported file/symbol evidence,
step dependencies, risks, assumptions, unresolved questions, and validation
commands proposed for later execution. Step identifiers must be unique and all
dependencies must point to another step.

Repository evidence is distinct from generated recommendations: a file or
symbol may be named in a plan only when it appears in the supplied packet.
Risks, assumptions, and validation commands are model-generated suggestions,
not claims that those actions or facts have already occurred. Malformed JSON,
invalid schemas, unsupported evidence, duplicate identifiers, and unknown
dependencies are rejected. The phase remains read-only and performs no shell
commands, file writes, patches, retries, or autonomous repairs.

Example shape:

```json
{
  "summary": "Add bounded planning",
  "objective": "Turn a coding task into an evidence-backed plan",
  "steps": [{"id": "inspect", "description": "Review src/app.py", "files": ["src/app.py"]}],
  "evidence_files": ["src/app.py"],
  "evidence_symbols": [],
  "risks": ["The requested behavior may need a product decision"],
  "assumptions": [],
  "unresolved_questions": [],
  "validation_commands": ["pytest"]
}
```

## Phase 9.3 controlled tool execution

`ToolExecutor` is the sole execution boundary for the agent harness. Its
registry contains only four read-only tools: repository search, file
inspection, dependency retrieval, and bounded context-packet assembly. Each
definition has a stable name, a Pydantic input schema, a description, and a
`read_only` permission classification. Unknown names, extra arguments,
invalid paths, sensitive files, symlink escapes, and malformed inputs are
rejected before a handler runs.

The execution loop is bounded by a per-task call limit, per-call timeout, and
serialized output limit. It returns structured success/failure results and
sanitized history. Provider failures and internal exceptions become generic
safe errors; credentials and raw exception text are not returned. The model
cannot register tools, invoke recursion, run commands, write files, apply
patches, or access the network. Phase 9.3 intentionally has no mutation
capabilities; later phases must introduce separate approval and validation
boundaries.

## Phase 9.1 agent harness

The agent harness is a planning-only coordination layer over the existing
provider and context services:

```text
AgentTask
   |
   v
ContextOrchestrator.build() ---> bounded ContextPacket
   |
   v
LLMProvider.generate() --------> strict AgentModelResult JSON
   |                                  |
   +-- complete ----------------------+
   +-- continue --> bounded next iteration
                                      |
                                      v
                               AgentOutcome
```

`AgentHarness` owns task validation, execution state, iteration limits, model
response validation, and result reporting. `ContextOrchestrator` remains the
only context assembly path, and `LLMProvider` remains the provider boundary.
The harness does not select a model or duplicate retrieval and ranking logic.

### Trust boundaries

- Repository scanning and context assembly remain inside the existing
  Context Hub root and packet budget.
- The provider receives the task and bounded packet evidence through the
  existing provider abstraction. Provider credentials remain in the launching
  environment and are not copied into task or outcome models.
- Model output is treated as untrusted data and must validate as the typed
  `AgentModelResult` schema.
- The harness returns plans and reports only. It has no shell, subprocess,
  file-write, patch, or autonomous repair capability.

### Explicit non-goals

Phase 9.1 does not execute shell commands, modify repository files, apply
patches, retry-and-repair failures autonomously, or expose a new MCP tool.
Those capabilities require later Phase 9 milestones and separate approval,
validation, and safety boundaries.
