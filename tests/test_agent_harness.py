from pathlib import Path

import pytest

from context_hub.agent_harness import AgentHarness, AgentTask, ExecutionStatus
from context_hub.orchestration.models import ContextStatistics
from context_hub.providers import ProviderError
from context_hub.providers.config import ProviderSettings
from context_hub.providers.models import GenerationResponse


class FakePacket:
    files = []
    statistics = ContextStatistics(files_considered=2, files_selected=0, estimated_tokens=0)


class FakeOrchestrator:
    def __init__(self, root, provider, *, budget, settings):
        self.root, self.provider, self.budget, self.settings = root, provider, budget, settings

    def build(self, task):
        return FakePacket()


class Provider:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return GenerationResponse(text=response, model="test", provider="test")


def harness(provider):
    return AgentHarness(Path.cwd(), provider, settings=ProviderSettings(), orchestrator_type=FakeOrchestrator)


def test_agent_task_rejects_empty_task_and_invalid_bounds():
    with pytest.raises(ValueError):
        AgentTask(task=" ")
    with pytest.raises(ValueError):
        AgentTask(task="task", max_iterations=0)
    with pytest.raises(ValueError):
        AgentTask(task="task", max_files=101)
    with pytest.raises(ValueError):
        AgentTask(task="task", max_tokens=99)


def test_harness_returns_structured_plan_without_execution():
    provider = Provider('{"status":"complete","summary":"Plan ready","plan":["Inspect the module"],"next_steps":["Implement after review"]}')
    outcome = harness(provider).run("Improve the module")
    assert outcome.status == ExecutionStatus.COMPLETED
    assert outcome.plan == ["Inspect the module"]
    assert outcome.context_statistics["files_selected"] == 0
    assert len(provider.requests) == 1
    assert "Do not execute commands" in provider.requests[0].system


def test_harness_stops_at_iteration_limit():
    response = '{"status":"continue","summary":"Need more planning","plan":["Review dependencies"],"next_steps":["Continue"]}'
    outcome = harness(Provider(response, response, response)).run(AgentTask(task="task", max_iterations=2))
    assert outcome.status == ExecutionStatus.ITERATION_LIMIT
    assert outcome.iterations == 2
    assert len(outcome.steps) == 3  # context plus two bounded planning steps
    assert "maximum of 2" in outcome.error


def test_harness_handles_malformed_model_response():
    outcome = harness(Provider("not json")).run("task")
    assert outcome.status == ExecutionStatus.FAILED
    assert "malformed" in outcome.error


def test_harness_handles_provider_failure_without_raw_error():
    outcome = harness(Provider(ProviderError("API_KEY=secret-value"))).run("task")
    assert outcome.status == ExecutionStatus.FAILED
    assert "secret-value" not in (outcome.error or "")


def test_harness_handles_context_provider_failure():
    class BrokenOrchestrator(FakeOrchestrator):
        def build(self, task):
            raise ProviderError("provider failed")

    outcome = AgentHarness(Path.cwd(), Provider(), settings=ProviderSettings(), orchestrator_type=BrokenOrchestrator).run("task")
    assert outcome.status == ExecutionStatus.FAILED
    assert "context packet" in outcome.error
