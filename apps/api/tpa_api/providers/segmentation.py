from __future__ import annotations

import abc
from typing import Any
from tpa_api.providers.base import Provider


class SegmentationProvider(Provider):
    """
    Interface for promptable segmentation of raster inputs.
    Contract defined in platform/PROVIDER_INTERFACES.md.
    """

    @abc.abstractmethod
    def segment(
        self,
        image: bytes,
        prompts: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Segments an image based on prompts (or auto-segment if None).
        
        Args:
            image: Raw image bytes.
            prompts: Optional list of prompt objects (points, boxes).
            options: Provider-specific options.
            
        Returns:
            {
                "masks": [
                    {
                        "mask_png_base64": "...",
                        "label": "...",
                        "score": 0.95,
                        "bbox": [x, y, w, h]
                    }
                ],
                "confidence": 0.0
            }
        """
        pass
