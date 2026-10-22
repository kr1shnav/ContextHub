"""Provider-independent, planning-only agent harness foundation."""

from __future__ import annotations

import json
import re
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .orchestration import ContextBudget, ContextOrchestrator
from .orchestration.models import ContextPacket
from .providers import LLMProvider, ProviderError
from .providers.config import ProviderSettings
from .providers.models import GenerationRequest
from .providers.prompts import SYSTEM_PROMPT


class AgentTask(BaseModel):
    """Validated input for one planning-only harness run."""

    task: str
    max_iterations: int = Field(default=3, ge=1, le=10)
    max_files: int = Field(default=10, ge=1, le=100)
    max_tokens: int = Field(default=6000, ge=100, le=100000)

    @field_validator("task")
    @classmethod
    def task_must_not_be_empty(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("task must be a non-empty string")
        return value.strip()


class ExecutionStatus(StrEnum):
    PENDING = "pending"
    PLANNING = "planning"
    COMPLETED = "completed"
    FAILED = "failed"
    ITERATION_LIMIT = "iteration_limit"


class AgentModelResult(BaseModel):
    """Strict structured response requested from the model."""

    status: Literal["complete", "continue"] = "complete"
    summary: str
    plan: list[str] = Field(min_length=1, max_length=20)
    next_steps: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("summary")
    @classmethod
    def summary_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("summary must be a non-empty string")
        return value.strip()

    @field_validator("plan", "next_steps")
    @classmethod
    def normalize_steps(cls, values: list[str]) -> list[str]:
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("plan steps must be non-empty strings")
        return [value.strip() for value in values]


class AgentStep(BaseModel):
    """One observable harness step; no shell or file mutation is represented."""

    iteration: int = Field(ge=1)
    phase: Literal["context", "planning"]
    status: ExecutionStatus
    message: str
    result: AgentModelResult | None = None


class AgentExecutionState(BaseModel):
    """Bounded state accumulated during one harness run."""

    status: ExecutionStatus = ExecutionStatus.PENDING
    iteration: int = 0
    steps: list[AgentStep] = Field(default_factory=list)
    context_paths: list[str] = Field(default_factory=list)
    context_statistics: dict[str, int] = Field(default_factory=dict)


class AgentOutcome(BaseModel):
    """Safe final report for callers and future agent integrations."""

    task: str
    status: ExecutionStatus
    iterations: int = Field(ge=0)
    summary: str = ""
    plan: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    steps: list[AgentStep] = Field(default_factory=list)
    context_paths: list[str] = Field(default_factory=list)
    context_statistics: dict[str, int] = Field(default_factory=dict)
    error: str | None = None


class AgentHarness:
    """Coordinate bounded context planning without executing repository actions."""

    def __init__(
        self,
        root: Path,
        provider: LLMProvider,
        *,
        settings: ProviderSettings | None = None,
        orchestrator_type: type[ContextOrchestrator] = ContextOrchestrator,
    ) -> None:
        self.root = root.resolve()
        self.provider = provider
        self.settings = settings or ProviderSettings.from_env()
        self.orchestrator_type = orchestrator_type

    def run(self, task: AgentTask | str) -> AgentOutcome:
        """Build context and produce a bounded structured plan."""
        agent_task = AgentTask(task=task) if isinstance(task, str) else task
        if not isinstance(agent_task, AgentTask):
            raise TypeError("task must be an AgentTask or non-empty string")
        state = AgentExecutionState(status=ExecutionStatus.PLANNING)
        try:
            packet = self.orchestrator_type(
                self.root,
                self.provider,
                budget=ContextBudget(max_files=agent_task.max_files, max_tokens=agent_task.max_tokens),
                settings=self.settings,
            ).build(agent_task.task)
        except ProviderError:
            return self._failure(agent_task, state, "Context provider unavailable while building the context packet.")
        except Exception:
            return self._failure(agent_task, state, "Context packet could not be built from the repository.")

        self._record_context(state, packet)
        last_result: AgentModelResult | None = None
        for iteration in range(1, agent_task.max_iterations + 1):
            state.iteration = iteration
            try:
                result = self._plan(agent_task, packet)
            except ProviderError:
                state.steps.append(AgentStep(iteration=iteration, phase="planning", status=ExecutionStatus.FAILED, message="Provider unavailable during planning."))
                return self._failure(agent_task, state, "Context provider unavailable during planning.")
            except (json.JSONDecodeError, ValueError, TypeError):
                state.steps.append(AgentStep(iteration=iteration, phase="planning", status=ExecutionStatus.FAILED, message="Model returned malformed structured planning data."))
                return self._failure(agent_task, state, "Model returned malformed structured planning data.")
            except Exception:
                state.steps.append(AgentStep(iteration=iteration, phase="planning", status=ExecutionStatus.FAILED, message="Planning failed unexpectedly."))
                return self._failure(agent_task, state, "Planning failed unexpectedly.")
            last_result = result
            state.steps.append(AgentStep(iteration=iteration, phase="planning", status=ExecutionStatus.PLANNING, message="Structured plan generated.", result=result))
            if result.status == "complete":
                state.status = ExecutionStatus.COMPLETED
                return self._outcome(agent_task, state, result)

        state.status = ExecutionStatus.ITERATION_LIMIT
        return self._outcome(
            agent_task,
            state,
            last_result,
            error=f"Planning stopped after the maximum of {agent_task.max_iterations} iterations.",
        )

    def _plan(self, task: AgentTask, packet: ContextPacket) -> AgentModelResult:
        evidence = [
            {
                "path": item.path,
                "symbol": item.symbol,
                "source": item.source,
                "reason": item.reason,
                "content": item.content,
            }
            for item in packet.files
        ]
        prompt = json.dumps({"task": task.task, "context": evidence}, sort_keys=True)
        response = self.provider.generate(
            GenerationRequest(
                system=(
                    SYSTEM_PROMPT
                    + " You are a planning-only coding agent. Return exactly one JSON object with "
                    + "status ('complete' or 'continue'), summary, plan (non-empty string array), "
                    + "and next_steps (string array). Do not execute commands, edit files, or propose tool calls."
                ),
                user=prompt[: self.settings.max_context_chars],
                model=self.settings.model,
                temperature=self.settings.temperature,
                max_tokens=self.settings.max_tokens,
            )
        )
        return AgentModelResult.model_validate(_parse_json_object(response.text))

    @staticmethod
    def _record_context(state: AgentExecutionState, packet: ContextPacket) -> None:
        state.context_paths = [item.path for item in packet.files]
        state.context_statistics = packet.statistics.model_dump(mode="json")
        state.steps.append(AgentStep(iteration=0 + 1, phase="context", status=ExecutionStatus.PLANNING, message="Context packet assembled."))

    @staticmethod
    def _failure(task: AgentTask, state: AgentExecutionState, error: str) -> AgentOutcome:
        state.status = ExecutionStatus.FAILED
        return AgentOutcome(
            task=task.task,
            status=state.status,
            iterations=state.iteration,
            steps=state.steps,
            context_paths=state.context_paths,
            context_statistics=state.context_statistics,
            error=error,
        )

    @staticmethod
    def _outcome(task: AgentTask, state: AgentExecutionState, result: AgentModelResult | None, *, error: str | None = None) -> AgentOutcome:
        return AgentOutcome(
            task=task.task,
            status=state.status,
            iterations=state.iteration,
            summary=result.summary if result else "",
            plan=result.plan if result else [],
            next_steps=result.next_steps if result else [],
            steps=state.steps,
            context_paths=state.context_paths,
            context_statistics=state.context_statistics,
            error=error,
        )


def _parse_json_object(text: str) -> dict[str, object]:
    candidate = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, re.IGNORECASE | re.DOTALL)
    if fence:
        candidate = fence.group(1)
    else:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end < start:
            raise json.JSONDecodeError("No complete JSON object found", candidate, 0)
        candidate = candidate[start : end + 1]
    data = json.loads(candidate)
    if not isinstance(data, dict):
        raise TypeError("Agent result must be a JSON object")
    return data
