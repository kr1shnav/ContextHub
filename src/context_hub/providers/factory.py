from .base import ProviderError
from .config import ProviderSettings
from .nebius import NebiusProvider
from .nvidia import NVIDIAProvider


def get_provider(settings: ProviderSettings | None = None):
    settings = settings or ProviderSettings.from_env()
    if settings.provider.lower() == "nebius": return NebiusProvider(settings)
    if settings.provider.lower() == "nvidia": return NVIDIAProvider(settings)
    raise ProviderError(f"Unsupported provider: {settings.provider}")
