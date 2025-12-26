from __future__ import annotations

import abc
from typing import Any
from tpa_api.providers.base import Provider


class VectorizationProvider(Provider):
    """
    Interface for converting raster images/masks to vector geometries.
    Contract defined in platform/PROVIDER_INTERFACES.md.
    """

    @abc.abstractmethod
    def vectorize(
        self,
        image: bytes,
        prompts: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Vectorizes a raster input.
        
        Args:
            image: Raw image/mask bytes (PNG/JPEG).
            prompts: Optional hints.
            options: Provider-specific options.
            
        Returns:
            {
                "features_geojson": { "type": "FeatureCollection", "features": [...] },
                "confidence": 0.9,
                "limitations_text": "..."
            }
        """
        pass
