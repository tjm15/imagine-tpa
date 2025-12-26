from __future__ import annotations

import abc
from typing import Any
from tpa_api.providers.base import Provider


class DocParseProvider(Provider):
    """
    Interface for parsing documents into a normalized structure.
    Contract defined in platform/PROVIDER_INTERFACES.md.
    """

    @abc.abstractmethod
    def parse_document(
        self,
        blob_path: str,
        file_bytes: bytes,
        filename: str,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Parses a document (PDF) into a DocParseResult structure.
        
        Args:
            blob_path: The storage path of the blob (for reference/logging).
            file_bytes: The raw bytes of the file.
            filename: The original filename (for type detection/logging).
            options: Optional parsing parameters.
            
        Returns:
            A dictionary conforming to the DocParseResult structure (pages, chunks, tables, etc.).
            Must include 'parse_bundle_path' if the result was stored as a bundle.
        """
        pass
