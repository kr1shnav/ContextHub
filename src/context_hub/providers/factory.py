from .base import ProviderError
from .config import ProviderSettings
from .nebius import NebiusProvider


def get_provider(settings: ProviderSettings | None = None):
    settings = settings or ProviderSettings.from_env()
    if settings.provider.lower() == "nebius": return NebiusProvider(settings)
    raise ProviderError(f"Unsupported provider: {settings.provider}")
