# Context Hub architecture

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
