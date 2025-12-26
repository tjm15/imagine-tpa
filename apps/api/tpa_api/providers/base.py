from __future__ import annotations

import abc
from typing import Any


class Provider(abc.ABC):
    """
    Base class for all providers.
    Every concrete provider must declare a profile_family ('azure' or 'oss').
    """

    @property
    @abc.abstractmethod
    def profile_family(self) -> str:
        """The profile family this provider belongs to."""
        pass


class BlobStoreProvider(Provider):
    """
    Interface for durable object storage for raw inputs and derived artefacts.
    Contract defined in platform/PROVIDER_INTERFACES.md.
    """

    @abc.abstractmethod
    def put_blob(
        self,
        path: str,
        data: bytes,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Stores a blob and returns metadata.
        Returns: {path, etag, size_bytes}
        """
        pass

    @abc.abstractmethod
    def get_blob(self, path: str) -> dict[str, Any]:
        """
        Retrieves a blob and its metadata.
        Returns: {bytes, content_type, metadata}
        """
        pass

    @abc.abstractmethod
    def delete_blob(self, path: str) -> None:
        """Deletes a blob."""
        pass

    @abc.abstractmethod
    def exists(self, path: str) -> bool:
        """Checks if a blob exists."""
        pass
