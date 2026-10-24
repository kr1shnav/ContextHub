"""Structural and explicitly opted-in validation for change proposals."""
from __future__ import annotations

import hashlib
import subprocess
import sys
import re
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict

from .mcp_server import _safe_repository_file
from .proposals import ChangeProposal, ProposalGenerator, ProposalLimits

_SECRET_ASSIGNMENT = re.compile(r"(?im)(\b(?:[a-z0-9]+[_-])?(?:api[_-]?key|access[_-]?key|secret|password|token)\b\s*[:=]\s*)([\"']?)[^\s\"']+")
_BEARER = re.compile(r"(?i)(\bBearer\s+)[^\s]+")


def _redact_output(value: str) -> str:
    value = _SECRET_ASSIGNMENT.sub(r"\1\2<redacted>", value)
    return _BEARER.sub(r"\1<redacted>", value)


class ValidationStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_RUN = "not_run"
    INCOMPLETE = "incomplete"


class CheckKind(StrEnum):
    PYTEST = "pytest"
    PY_COMPILE = "py_compile"


class ValidationCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: CheckKind
    path: str | None = Field(default=None, max_length=500)


class CheckResult(BaseModel):
    kind: CheckKind
    status: ValidationStatus
    exit_code: int | None = None
    summary: str = ""
    output: str = ""


class ValidationReport(BaseModel):
    proposal_id: str
    status: ValidationStatus
    static_validation: list[str] = Field(default_factory=list)
    checks: list[CheckResult] = Field(default_factory=list)
    failure_output: str = ""
    limitations: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class ValidationRequest(BaseModel):
    checks: list[ValidationCheck] = Field(default_factory=list, max_length=10)
    execute: bool = False
    timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    max_output_chars: int = Field(default=12000, ge=100, le=100000)


class ProposalValidator:
    """Validate proposals without changing the working tree."""

    def __init__(self, root: Path, *, limits: ProposalLimits | None = None):
        self.root = root.resolve()
        self.limits = limits or ProposalLimits()

    def validate(self, proposal: ChangeProposal, request: ValidationRequest | None = None) -> ValidationReport:
        request = request or ValidationRequest()
        proposal_id = hashlib.sha256(proposal.model_dump_json().encode()).hexdigest()[:16]
        static: list[str] = []
        try:
            generator = ProposalGenerator(self.root, provider=_NoProvider(), limits=self.limits)
            generator._validate(proposal, _EvidencePacket(proposal))
            static.append("Patch structure, target paths, repository boundaries, and configured limits are valid.")
        except Exception:
            return ValidationReport(proposal_id=proposal_id, status=ValidationStatus.FAILED, static_validation=["Static proposal validation failed."], limitations=["Executable checks were not attempted."], risks=proposal.risks, next_steps=["Review the proposal and regenerate a valid patch."], failure_output="Proposal failed static validation.")
        checks: list[CheckResult] = []
        if not request.execute:
            checks = [CheckResult(kind=check.kind, status=ValidationStatus.NOT_RUN, summary="Not run; explicit execution opt-in was not provided.") for check in request.checks]
            return ValidationReport(proposal_id=proposal_id, status=ValidationStatus.PASSED if not checks else ValidationStatus.NOT_RUN, static_validation=static, checks=checks, limitations=["Tests and syntax checks were not run; this report covers structural validation only.", "Any later checks run against the current working tree, not an applied proposal."], risks=proposal.risks, next_steps=["Review the diff, then explicitly opt in to approved checks."])
        for check in request.checks:
            checks.append(self._run_check(check, request.timeout_seconds, request.max_output_chars))
        status = ValidationStatus.FAILED if any(c.status == ValidationStatus.FAILED for c in checks) else ValidationStatus.PASSED
        failures = "\n".join(c.output for c in checks if c.status == ValidationStatus.FAILED and c.output)
        return ValidationReport(proposal_id=proposal_id, status=status, static_validation=static, checks=checks, failure_output=failures[:request.max_output_chars], limitations=["Checks run against the current working tree; the proposal was not applied."], risks=proposal.risks, next_steps=["Review failures before deciding whether to revise the proposal."])

    def _run_check(self, check: ValidationCheck, timeout: float, max_output: int) -> CheckResult:
        if check.kind == CheckKind.PYTEST:
            command = [sys.executable, "-m", "pytest"]
        elif check.kind == CheckKind.PY_COMPILE:
            if not check.path: return CheckResult(kind=check.kind, status=ValidationStatus.FAILED, summary="A repository-relative path is required.")
            try: target = _safe_repository_file(self.root, check.path)
            except Exception: return CheckResult(kind=check.kind, status=ValidationStatus.FAILED, summary="Invalid repository path.")
            if target.suffix.lower() != ".py": return CheckResult(kind=check.kind, status=ValidationStatus.FAILED, summary="Only Python files may be syntax checked.")
            command = [sys.executable, "-m", "py_compile", target.relative_to(self.root).as_posix()]
        try:
            completed = subprocess.run(command, cwd=self.root, shell=False, capture_output=True, text=True, timeout=timeout, check=False)
            output = _redact_output((completed.stdout or "") + (completed.stderr or ""))[:max_output]
            return CheckResult(kind=check.kind, status=ValidationStatus.PASSED if completed.returncode == 0 else ValidationStatus.FAILED, exit_code=completed.returncode, summary="Command completed successfully." if completed.returncode == 0 else "Command returned a nonzero exit code.", output=output)
        except subprocess.TimeoutExpired:
            return CheckResult(kind=check.kind, status=ValidationStatus.FAILED, summary="Command timed out; no result is treated as passing.")
        except OSError:
            return CheckResult(kind=check.kind, status=ValidationStatus.INCOMPLETE, summary="Approved command could not be started.")


class _NoProvider:
    pass


class _EvidencePacket:
    def __init__(self, proposal: ChangeProposal):
        self.files = [type("Evidence", (), {"path": item.path})() for item in proposal.files]
