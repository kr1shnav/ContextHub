import httpx
import pytest

from context_hub.providers import NVIDIAProvider, ProviderError, get_provider
from context_hub.providers.config import ProviderSettings
from context_hub.providers.models import GenerationRequest


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
