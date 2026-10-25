import httpx
import json
import pytest
from typer.testing import CliRunner

from context_hub.providers import NVIDIAProvider, NebiusProvider, ProviderError, get_provider
from context_hub.providers.config import ProviderSettings
from context_hub.providers.models import GenerationRequest
from context_hub.analysis import analyze_task
from context_hub.providers.models import GenerationResponse
from pathlib import Path
from context_hub.orchestration import ContextBudget, ContextOrchestrator
from context_hub.cli import app


def request() -> GenerationRequest:
    return GenerationRequest(system="system", user="user")


def test_nvidia_provider_uses_catalog_endpoint_and_bearer_key():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(url=str(request.url), auth=request.headers["authorization"], model=request.read().decode())
        return httpx.Response(200, json={"model": "nvidia/nemotron-3-super-120b-a12b", "choices": [{"message": {"content": "{}"}}]})

    settings = ProviderSettings(provider="nvidia", model="nvidia/nemotron-3-super-120b-a12b", api_key="test-key", base_url="https://integrate.api.nvidia.com/v1")
    response = NVIDIAProvider(settings, httpx.Client(transport=httpx.MockTransport(handler))).generate(request())
    assert response.provider == "NVIDIA"
    assert seen["url"] == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert seen["auth"] == "Bearer test-key"
    assert "test-key" not in seen["model"]
    body = json.loads(seen["model"])
    assert body["model"] == "nvidia/nemotron-3-super-120b-a12b"
    assert body["response_format"] == {"type": "json_object"}
    assert body["reasoning_effort"] == "none"


def test_nvidia_completion_path_is_appended_once():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    for base_url in ("https://integrate.api.nvidia.com/v1", "https://integrate.api.nvidia.com/v1/", "https://integrate.api.nvidia.com/v1/chat/completions"):
        settings = ProviderSettings(provider="nvidia", model="nvidia/test-model", api_key="test-key", base_url=base_url)
        NVIDIAProvider(settings, httpx.Client(transport=httpx.MockTransport(handler))).generate(request())

    assert seen == ["https://integrate.api.nvidia.com/v1/chat/completions"] * 3


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, "HTTP 401"),
        (403, "HTTP 403"),
        (404, "HTTP 404"),
        (429, "HTTP 429"),
        (503, "HTTP 503"),
    ],
)
def test_nvidia_provider_preserves_http_error_status(status, expected):
    settings = ProviderSettings(provider="nvidia", api_key="test-key", base_url="https://example.test/v1")
    provider = NVIDIAProvider(settings, httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status, json={"error": {"message": "catalog detail"}}))))
    with pytest.raises(ProviderError, match=expected) as error:
        provider.generate(request())
    assert "catalog detail" in str(error.value)


def test_nvidia_account_entitlement_error_is_actionable():
    settings = ProviderSettings(provider="nvidia", api_key="test-key", base_url="https://example.test/v1")
    provider = NVIDIAProvider(
        settings,
        httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(404, json={"detail": "Function 'function-id': Not found for account 'account-id'"})
        )),
    )
    with pytest.raises(ProviderError, match="account-scoped 404") as error:
        provider.generate(request())
    assert "nvidia/nemotron-3-super-120b-a12b" in str(error.value)
    assert "account-id" not in str(error.value)
    assert "function-id" not in str(error.value)
    assert "test-key" not in str(error.value)


def test_nvidia_generic_404_includes_model_and_handles_plain_text_safely():
    settings = ProviderSettings(provider="nvidia", model="nvidia/test-model", api_key="test-key", base_url="https://example.test/v1")
    provider = NVIDIAProvider(
        settings,
        httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(404, text="route missing; Bearer test-key; account account-id")
        )),
    )
    with pytest.raises(ProviderError, match="model 'nvidia/test-model' or endpoint was not found") as error:
        provider.generate(request())
    assert "test-key" not in str(error.value)
    assert "account-id" not in str(error.value)


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (httpx.Response(200, text="<html>gateway error</html>", headers={"content-type": "text/html"}), "invalid JSON"),
        (httpx.Response(200, json=[]), "expected an object"),
        (httpx.Response(200, json={"choices": []}), "missing a non-empty 'choices'"),
        (httpx.Response(200, json={"choices": [{}]}), r"missing 'choices\[0\].message'"),
        (httpx.Response(200, json={"choices": [{"message": {}}]}), r"'choices\[0\]\.message\.content' is missing"),
        (httpx.Response(200, json={"choices": [{"message": {"content": ""}}]}), r"'choices\[0\]\.message\.content' is empty or invalid"),
    ],
)
def test_nvidia_provider_reports_response_shape_errors(response, expected):
    settings = ProviderSettings(provider="nvidia", api_key="test-key", base_url="https://example.test/v1")
    malformed = NVIDIAProvider(settings, httpx.Client(transport=httpx.MockTransport(lambda request: response)))
    with pytest.raises(ProviderError, match=expected):
        malformed.generate(request())


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ({"content": "", "reasoning_content": "private reasoning"}, "will not substitute private reasoning"),
        ({"content": "", "tool_calls": [{"id": "call-1"}]}, "does not support tool-call execution"),
        ({"content": "", "refusal": "not allowed"}, "refused the task-analysis request"),
    ],
)
def test_nvidia_provider_reports_non_text_completion_modes(message, expected):
    settings = ProviderSettings(provider="nvidia", api_key="test-key", base_url="https://example.test/v1")
    provider = NVIDIAProvider(
        settings,
        httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"choices": [{"message": message, "finish_reason": "stop"}]})
        )),
    )
    with pytest.raises(ProviderError, match=expected):
        provider.generate(request())


def test_nvidia_provider_reports_length_limited_empty_completion():
    settings = ProviderSettings(provider="nvidia", api_key="test-key", base_url="https://example.test/v1")
    provider = NVIDIAProvider(
        settings,
        httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"choices": [{"message": {"content": ""}, "finish_reason": "length"}]})
        )),
    )
    with pytest.raises(ProviderError, match="finish_reason='length'"):
        provider.generate(request())


def test_nvidia_provider_accepts_structured_text_content():
    settings = ProviderSettings(provider="nvidia", api_key="test-key", base_url="https://example.test/v1")
    provider = NVIDIAProvider(
        settings,
        httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"choices": [{"message": {"content": [{"type": "text", "text": "{"}, {"type": "text", "text": "}"}]}}]})
        )),
    )
    assert provider.generate(request()).text == "{}"


def test_nvidia_provider_accepts_openai_compatible_success_response():
    settings = ProviderSettings(provider="nvidia", api_key="test-key", base_url="https://example.test/v1")
    provider = NVIDIAProvider(
        settings,
        httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={
                "id": "completion-id",
                "model": "nvidia/test-model",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "{}"}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                    "prompt_tokens_details": {"cached_tokens": 0},
                    "completion_tokens_details": {"reasoning_tokens": 3},
                    "provider_specific": {"accounting_version": "v1"},
                },
            })
        )),
    )
    response = provider.generate(request())
    assert response.text == "{}"
    assert response.finish_reason == "stop"
    assert response.usage["prompt_tokens"] == 1
    assert response.usage["prompt_tokens_details"] == {"cached_tokens": 0}


def test_generation_response_allows_missing_usage_and_rejects_bad_token_counts():
    from context_hub.providers.models import GenerationResponse

    assert GenerationResponse(text="{}", model="test", provider="NVIDIA").usage is None
    with pytest.raises(ValueError, match="usage.prompt_tokens must be an integer"):
        GenerationResponse(text="{}", model="test", provider="NVIDIA", usage={"prompt_tokens": "1"})


def test_nvidia_selection_and_missing_key(monkeypatch):
    monkeypatch.setenv("CONTEXT_HUB_PROVIDER", "nvidia")
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    settings = ProviderSettings.from_env()
    assert isinstance(get_provider(settings), NVIDIAProvider)
    with pytest.raises(ProviderError, match="NVIDIA_API_KEY"):
        get_provider(settings).generate(request())


def test_provider_settings_load_selected_nvidia_values(monkeypatch):
    monkeypatch.setenv("CONTEXT_HUB_PROVIDER", " NVIDIA ")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvidia-test-key")
    monkeypatch.setenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    monkeypatch.setenv("NVIDIA_MODEL", "nvidia/nemotron-3.5-super-vl-120b-a12b")
    monkeypatch.setenv("NVIDIA_REASONING_EFFORT", "low")
    monkeypatch.setenv("NEBIUS_API_KEY", "nebius-must-not-be-used")
    settings = ProviderSettings.from_env()
    assert settings.provider == "nvidia"
    assert settings.api_key == "nvidia-test-key"
    assert settings.base_url == "https://integrate.api.nvidia.com/v1"
    assert settings.model == "nvidia/nemotron-3.5-super-vl-120b-a12b"
    assert settings.reasoning_effort == "low"
    assert isinstance(get_provider(settings), NVIDIAProvider)


def test_nebius_selection_remains_explicit(monkeypatch):
    monkeypatch.setenv("CONTEXT_HUB_PROVIDER", "nebius")
    monkeypatch.setenv("NEBIUS_API_KEY", "nebius-test-key")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvidia-must-not-be-used")
    settings = ProviderSettings.from_env()
    assert settings.provider == "nebius"
    assert isinstance(get_provider(settings), NebiusProvider)


def test_nebius_openai_compatible_success_remains_supported():
    settings = ProviderSettings(provider="nebius", api_key="test-key", base_url="https://example.test/v1")
    provider = NebiusProvider(
        settings,
        httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"model": "test-model", "choices": [{"message": {"content": "{}"}}]})
        )),
    )
    assert provider.generate(request()).text == "{}"


def test_provider_status_uses_selected_provider_without_network(monkeypatch):
    monkeypatch.setenv("CONTEXT_HUB_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvidia-test-key")
    monkeypatch.setenv("NVIDIA_MODEL", "nvidia/test-model")
    result = CliRunner().invoke(app, ["provider", "status"])
    assert result.exit_code == 0
    assert "Provider: Nvidia" in result.stdout
    assert "Model: nvidia/test-model" in result.stdout
    assert "API key: configured" in result.stdout
    assert "nvidia-test-key" not in result.stdout


def test_analyze_explicit_nvidia_missing_key_does_not_fall_back(monkeypatch):
    monkeypatch.setenv("CONTEXT_HUB_PROVIDER", "nvidia")
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setenv("NEBIUS_API_KEY", "nebius-must-not-be-used")
    result = CliRunner().invoke(app, ["analyze", "Explain the architecture"])
    assert result.exit_code == 1
    assert "NVIDIA API key is not configured" in result.stdout
    assert "NEBIUS" not in result.stdout


def test_task_analysis_accepts_fenced_and_surrounded_json(tmp_path: Path):
    payload = '{"task_type":"explanation","confidence":0.8,"reasoning":"valid"}'

    class Provider:
        def generate(self, request):
            return GenerationResponse(text="Here is the result:\n```json\n" + payload + "\n```", model="test", provider="test")

    result = analyze_task("Explain this", Provider(), tmp_path)
    assert result.task == "Explain this"
    assert result.task_type == "explanation"


def test_task_analysis_accepts_null_optional_lists(tmp_path: Path):
    class Provider:
        def generate(self, request):
            return GenerationResponse(text='{"task_type":"task","domains":null,"confidence":0.5,"reasoning":"valid"}', model="test", provider="test")

    assert analyze_task("Explain this", Provider(), tmp_path).domains == []


def test_task_analysis_ignores_provider_usage_metadata_but_keeps_strict_fields(tmp_path: Path):
    class Provider:
        def generate(self, request):
            return GenerationResponse(
                text='{"task_type":"explanation","confidence":0.8,"reasoning":"valid",'
                     '"usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15,'
                     '"prompt_tokens_details":{"cached_tokens":2},'
                     '"completion_tokens_details":{"reasoning_tokens":3},'
                     '"provider_field":{"value":"ignored"}}}',
                model="test", provider="NVIDIA",
                usage={"prompt_tokens": 10, "prompt_tokens_details": {"cached_tokens": 2}},
            )

    result = analyze_task("Explain this", Provider(), tmp_path)
    assert result.task_type == "explanation"


def test_task_analysis_rejects_wrong_required_field_type_with_usage_metadata(tmp_path: Path):
    class Provider:
        def generate(self, request):
            return GenerationResponse(
                text='{"task_type":"explanation","confidence":"high","reasoning":"invalid",'
                     '"usage":{"prompt_tokens":10,"prompt_tokens_details":{"cached_tokens":2}}}',
                model="test", provider="NVIDIA",
            )

    with pytest.raises(ProviderError, match="confidence"):
        analyze_task("Explain this", Provider(), tmp_path)


def test_task_analysis_retries_malformed_output_once(tmp_path: Path):
    class Provider:
        calls = 0

        def generate(self, request):
            self.calls += 1
            text = "not json" if self.calls == 1 else '{"task_type":"task","confidence":0.5,"reasoning":"retry"}'
            return GenerationResponse(text=text, model="test", provider="test")

    provider = Provider()
    assert analyze_task("Explain this", provider, tmp_path).reasoning == "retry"
    assert provider.calls == 2


@pytest.mark.parametrize("text", ["not json", '{"task_type":"task"}', '{"task_type":"task","confidence":0.5'])
def test_task_analysis_rejects_invalid_or_incomplete_output(tmp_path: Path, text: str):
    class Provider:
        def generate(self, request):
            return GenerationResponse(text=text, model="test", provider="test")

    with pytest.raises(ProviderError, match="malformed task analysis JSON"):
        analyze_task("Explain this", Provider(), tmp_path)


def test_context_pack_bounds_analysis_prompt_and_assembles_packet(tmp_path: Path):
    (tmp_path / "orchestrator.py").write_text("class ContextOrchestrator:\n    pass\n")
    calls = []

    class Provider:
        def generate(self, request):
            calls.append(request)
            if len(calls) == 1:
                return GenerationResponse(text='{"task_type":"explanation","domains":["orchestration"],"keywords":["context"],"likely_files":["orchestrator.py"],"confidence":0.8,"reasoning":"valid"}', model="test", provider="test")
            return GenerationResponse(text='{"priority_paths":[],"important_symbols":[],"reasoning":"valid"}', model="test", provider="test")

    packet = ContextOrchestrator(tmp_path, Provider(), budget=ContextBudget(max_files=3, max_tokens=1000)).build("Explain the context packet", limit=20)
    assert packet.task_analysis.task_type == "explanation"
    assert len(calls) == 2
    assert "Bounded repository retrieval metadata" in calls[0].user
    assert "Keep the arrays concise" in calls[0].user
