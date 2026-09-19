"""Which model client the app uses, from its settings."""

import httpx

from app.copilot.fake import FakeModelClient
from app.copilot.model import ModelClient
from app.copilot.openrouter import OpenRouterClient
from app.core.config import Settings


def create_model_client(settings: Settings, http: httpx.AsyncClient) -> ModelClient | None:
    """The offline fake when COPILOT_FAKE_MODEL is on (never in production), OpenRouter when a
    key is set, and otherwise None: the Copilot is unavailable.
    """
    if settings.copilot_fake_model:
        return FakeModelClient()
    key = settings.copilot_key
    if key is None:
        return None
    return OpenRouterClient(
        http=http,
        api_key=key,
        base_url=settings.openrouter_base_url,
        model=settings.copilot_model,
        max_output_tokens=settings.copilot_max_output_tokens,
    )
