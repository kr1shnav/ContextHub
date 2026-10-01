from .base import LLMProvider
from .models import GenerationRequest, GenerationResponse


class MockProvider(LLMProvider):
    name = "Mock"

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        return GenerationResponse(text='{"task_type":"task","domains":[],"keywords":[],"likely_files":[],"likely_symbols":[],"required_context":[],"ambiguities":[],"constraints":[],"confidence":0.5,"reasoning":"Deterministic mock analysis."}', model="mock", provider=self.name)
