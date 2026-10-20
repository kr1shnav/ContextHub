import httpx
import pytest

from context_hub.providers import NVIDIAProvider, ProviderError, get_provider
from context_hub.providers.config import ProviderSettings
from context_hub.providers.models import GenerationRequest
from context_hub.analysis import analyze_task
from context_hub.providers.models import GenerationResponse
from pathlib import Path


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


def test_nvidia_provider_maps_malformed_response():
    settings = ProviderSettings(provider="nvidia", api_key="test-key", base_url="https://example.test/v1")
    malformed = NVIDIAProvider(settings, httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": []}))))
    with pytest.raises(ProviderError, match="invalid response"):
        malformed.generate(request())


def test_nvidia_selection_and_missing_key(monkeypatch):
    monkeypatch.setenv("CONTEXT_HUB_PROVIDER", "nvidia")
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    settings = ProviderSettings.from_env()
    assert isinstance(get_provider(settings), NVIDIAProvider)
    with pytest.raises(ProviderError, match="NVIDIA_API_KEY"):
        get_provider(settings).generate(request())


def test_task_analysis_accepts_fenced_and_surrounded_json(tmp_path: Path):
    payload = '{"task_type":"explanation","confidence":0.8,"reasoning":"valid"}'

    class Provider:
        def generate(self, request):
            return GenerationResponse(text="Here is the result:\n```json\n" + payload + "\n```", model="test", provider="test")

    result = analyze_task("Explain this", Provider(), tmp_path)
    assert result.task == "Explain this"
    assert result.task_type == "explanation"


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
