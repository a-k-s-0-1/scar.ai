"""Client for local Ollama instance (Tier 1 local model routing)."""

import httpx

from app.api.errors import ExternalAPIError
from app.config import get_settings
from app.utils.logger import logger

settings = get_settings()


class OllamaClient:
    """Client for local Ollama API (http://localhost:11434)."""

    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        self.timeout = httpx.Timeout(15.0, connect=3.0)

    async def is_available(self) -> bool:
        """Check if local Ollama daemon is reachable."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(2.0)) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                return res.status_code == 200
        except Exception:
            return False

    async def generate(self, prompt: str, system: str | None = None) -> str:
        """Call Ollama /api/generate endpoint."""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("response", "")
        except Exception as e:
            logger.warning(f"Ollama local generation failed: {e}")
            raise ExternalAPIError("Ollama", str(e)) from e
