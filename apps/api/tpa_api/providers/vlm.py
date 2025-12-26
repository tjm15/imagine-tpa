from __future__ import annotations

import abc
from typing import Any
from tpa_api.providers.base import Provider


class VLMProvider(Provider):
    """
    Interface for multimodal understanding of plans/images/figures.
    Contract defined in platform/PROVIDER_INTERFACES.md.
    """

    @abc.abstractmethod
    def generate_structured(
        self,
        messages: list[dict[str, str]],
        images: list[bytes],
        json_schema: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Generates structured JSON output from a VLM given text messages and images.
        
        Args:
            messages: List of message dicts (role, content).
            images: List of raw image bytes (PNG/JPEG).
            json_schema: Optional JSON schema for validation/constrained generation.
            options: Provider-specific options (model_id, temperature, etc.).
            
        Returns:
            {
                "json": dict | None,
                "usage": dict,
                "model_id": str,
                "raw_text": str | None,
                "tool_run_id": str
            }
        """
        pass
