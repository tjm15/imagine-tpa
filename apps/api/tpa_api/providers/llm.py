from __future__ import annotations

import abc
from typing import Any
from tpa_api.providers.base import Provider


class LLMProvider(Provider):
    """
    Interface for grammar-bound reasoning and synthesis (text only).
    Contract defined in platform/PROVIDER_INTERFACES.md.
    """

    @abc.abstractmethod
    def generate_structured(
        self,
        messages: list[dict[str, str]],
        json_schema: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Generates structured JSON output from an LLM.
        
        Args:
            messages: List of message dicts (role, content).
            json_schema: Optional JSON schema for validation/constrained generation.
            options: Provider-specific options (model_id, temperature, etc.).
            
        Returns:
            {
                "json": dict | None,
                "usage": dict,
                "model_id": str,
                "raw_text": str | None
            }
        """
        pass
