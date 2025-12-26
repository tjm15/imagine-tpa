from __future__ import annotations

import os
from tpa_api.providers.base import BlobStoreProvider
from tpa_api.providers.oss_blob import MinIOBlobStoreProvider


from tpa_api.providers.docparse import DocParseProvider
from tpa_api.providers.docparse_http import HttpDocParseProvider
from tpa_api.providers.segmentation import SegmentationProvider
from tpa_api.providers.segmentation_http import HttpSegmentationProvider
from tpa_api.providers.vectorization import VectorizationProvider
from tpa_api.providers.vectorization_http import HttpVectorizationProvider
from tpa_api.providers.llm import LLMProvider
from tpa_api.providers.llm_openai import OpenAILLMProvider
from tpa_api.providers.vlm import VLMProvider
from tpa_api.providers.vlm_openai import OpenAIVLMProvider


def get_blob_store_provider() -> BlobStoreProvider:
    """
    Returns the configured BlobStoreProvider.
    Currently only supports 'oss' (MinIO).
    """
    profile = os.environ.get("TPA_PROFILE", "oss")
    if profile == "oss":
        return MinIOBlobStoreProvider()
    
    # In a full implementation, we'd check for 'azure' and return AzureBlobStoreProvider
    # For now, default to OSS or raise if specifically requested and missing.
    if profile == "azure":
        raise NotImplementedError("AzureBlobStoreProvider not implemented yet")
        
    return MinIOBlobStoreProvider()


def get_docparse_provider() -> DocParseProvider:
    """
    Returns the configured DocParseProvider.
    """
    # Currently only one implementation exists
    return HttpDocParseProvider()


def get_segmentation_provider() -> SegmentationProvider:
    """
    Returns the configured SegmentationProvider.
    """
    return HttpSegmentationProvider()


def get_vectorization_provider() -> VectorizationProvider:
    """
    Returns the configured VectorizationProvider.
    """
    return HttpVectorizationProvider()


def get_llm_provider() -> LLMProvider:
    """
    Returns the configured LLMProvider.
    """
    return OpenAILLMProvider()


def get_vlm_provider() -> VLMProvider:
    """
    Returns the configured VLMProvider.
    """
    return OpenAIVLMProvider()
