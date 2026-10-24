"""Read-only, evidence-bounded unified-diff proposal generation."""
from __future__ import annotations

import json
import re
from pathlib import Path, PureWindowsPath
from typing import Any

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

from .agent_harness import AgentTask, RepositoryPlan, _parse_json_object
from .mcp_server import _is_sensitive_path, _safe_repository_file, _validate_relative_path
from .orchestration import ContextBudget, ContextOrchestrator
from .orchestration.models import ContextPacket
from .providers import LLMProvider, ProviderError
from .providers.config import ProviderSettings
from .providers.models import GenerationRequest
from .providers.prompts import SYSTEM_PROMPT


class ProposedFileDiff(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=500)
    patch: str = Field(min_length=1, max_length=50000)

    @field_validator("path")
    @classmethod
    def path_is_relative(cls, value: str) -> str:
        normalized = _validate_relative_path(value)
        if _is_sensitive_path(normalized):
            raise ValueError("sensitive files cannot be proposed")
        return normalized


class ChangeProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=500)
    rationale: str = Field(min_length=1, max_length=2000)
    files: list[ProposedFileDiff] = Field(min_length=1, max_length=20)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    risks: list[str] = Field(default_factory=list, max_length=20)
    validation_recommendations: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def unique_files(self) -> "ChangeProposal":
        paths = [item.path for item in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("proposal contains duplicate file paths")
        return self


class ProposalLimits(BaseModel):
    max_files: int = Field(default=5, ge=1, le=20)
    max_patch_chars: int = Field(default=60000, ge=1000, le=300000)
    max_output_tokens: int = Field(default=4000, ge=100, le=20000)


class ProposalGenerator:
    def __init__(self, root: Path, provider: LLMProvider, *, settings: ProviderSettings | None = None, limits: ProposalLimits | None = None):
        self.root = root.resolve(); self.provider = provider; self.settings = settings or ProviderSettings.from_env(); self.limits = limits or ProposalLimits()

    def generate(self, task: AgentTask | str, *, plan: RepositoryPlan | None = None, packet: ContextPacket | None = None) -> ChangeProposal:
        agent_task = AgentTask(task=task) if isinstance(task, str) else task
        if not isinstance(agent_task, AgentTask): raise TypeError("task must be an AgentTask or non-empty string")
        packet = packet or ContextOrchestrator(self.root, self.provider, budget=ContextBudget(max_files=agent_task.max_files, max_tokens=agent_task.max_tokens), settings=self.settings).build(agent_task.task)
        evidence = [{"path": item.path, "symbol": item.symbol, "source": item.source, "reason": item.reason, "content": item.content} for item in packet.files]
        prompt = json.dumps({"task": agent_task.task, "task_plan": plan.model_dump() if plan else None, "repository_evidence": evidence}, sort_keys=True)
        response = self.provider.generate(GenerationRequest(
            system=SYSTEM_PROMPT + " You generate reviewable code-change proposals only. Return exactly one JSON object matching ChangeProposal with summary, rationale, files [{path, patch}], assumptions, risks, validation_recommendations. Each patch must be a unified diff for an existing repository file. Do not use absolute paths, traversal, sensitive files, or claim unsupported facts. Never apply the patch.",
            user=prompt[:self.settings.max_context_chars], model=self.settings.model, temperature=self.settings.temperature, max_tokens=min(self.settings.max_tokens, self.limits.max_output_tokens)))
        proposal = ChangeProposal.model_validate(_parse_json_object(response.text))
        self._validate(proposal, packet)
        return proposal

    def _validate(self, proposal: ChangeProposal, packet: ContextPacket) -> None:
        if len(proposal.files) > self.limits.max_files: raise ValueError("proposal exceeds file limit")
        total = sum(len(item.patch) for item in proposal.files)
        if total > self.limits.max_patch_chars: raise ValueError("proposal exceeds patch-size limit")
        evidence_paths = {item.path for item in packet.files}
        evidence_by_path = {item.path: item for item in packet.files}
        for item in proposal.files:
            target = self.root / item.path
            if not target.resolve().is_relative_to(self.root):
                raise ValueError("proposal target must stay inside repository")
            if not target.is_file():
                evidence = evidence_by_path.get(item.path)
                if evidence is None or evidence.content is None:
                    raise ValueError("proposal target must be an existing file or supplied as source evidence")
            if item.path not in evidence_paths:
                proposal.assumptions.append(f"Source evidence for {item.path} was not in the selected context.")
            self._validate_diff(item.path, item.patch, target)

    @staticmethod
    def _validate_diff(path: str, patch: str, target: Path) -> None:
        lines = patch.splitlines()
        if len(lines) < 4 or not lines[0].startswith("--- ") or not lines[1].startswith("+++ "):
            raise ValueError("patch is not a unified diff")
        header_paths = [lines[0][4:].split("\t")[0], lines[1][4:].split("\t")[0]]
        normalized = {p.removeprefix("a/").removeprefix("b/") for p in header_paths}
        if normalized != {path}:
            raise ValueError("patch headers do not match the proposed path")
        if not any(line.startswith("@@ ") for line in lines[2:]):
            raise ValueError("patch has no unified-diff hunk")
        if any(line.startswith(("*** ", "diff ", "GIT binary patch")) for line in lines):
            raise ValueError("unsupported patch format")

    def save(self, proposal: ChangeProposal, output_dir: Path, filename: str = "proposal.patch") -> Path:
        destination_root = (self.root / output_dir).resolve() if not output_dir.is_absolute() else output_dir.resolve()
        if not destination_root.is_relative_to(self.root): raise ValueError("output directory must stay inside repository")
        if not filename or Path(filename).name != filename or filename in {".", ".."} or _is_sensitive_path(filename): raise ValueError("unsafe proposal filename")
        destination_root.mkdir(parents=True, exist_ok=True)
        destination = (destination_root / filename).resolve()
        if not destination.is_relative_to(destination_root): raise ValueError("output path escapes output directory")
        text = "\n\n".join(item.patch.rstrip() for item in proposal.files) + "\n"
        if len(text) > self.limits.max_patch_chars: raise ValueError("proposal exceeds patch-size limit")
        destination.write_text(text, encoding="utf-8", newline="\n")
        return destination
