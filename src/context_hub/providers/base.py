from abc import ABC, abstractmethod
from .models import GenerationRequest, GenerationResponse


class ProviderError(RuntimeError):
    """Safe, user-facing provider failure without credentials or raw responses."""


class LLMProvider(ABC):
    name = "unknown"

    @abstractmethod
    def generate(self, request: GenerationRequest) -> GenerationResponse:
        raise NotImplementedError
