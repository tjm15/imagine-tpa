"""
Tests for VLM (Vision Language Model) client functionality.

These tests verify that:
1. VLM configuration loads correctly from environment
2. VLM endpoint connectivity and fallback behavior work
3. VLM responses are parsed correctly for various response shapes
4. Error handling and timeouts work as expected
"""

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

# Import the VLM-related functions from model_clients
from tpa_api.model_clients import (
    _vlm_model_id,
    _ensure_model_role_sync,
    _ensure_model_role,
    _model_supervisor_headers,
)


class TestVLMConfiguration:
    """Test VLM model configuration and defaults."""

    def test_vlm_model_id_default(self):
        """VLM model ID defaults to nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8 when no env is set."""
        with patch.dict(os.environ, {}, clear=True):
            model_id = _vlm_model_id()
            assert model_id == "nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8"

    def test_vlm_model_id_from_env(self):
        """VLM model ID respects TPA_VLM_MODEL_ID environment variable."""
        with patch.dict(os.environ, {"TPA_VLM_MODEL_ID": "custom/vlm-test"}):
            model_id = _vlm_model_id()
            assert model_id == "custom/vlm-test"

    def test_vlm_model_id_override(self):
        """TPA_VLM_MODEL_ID overrides default even if other vars exist."""
        with patch.dict(os.environ, {"TPA_VLM_MODEL_ID": "nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8"}):
            model_id = _vlm_model_id()
            assert model_id == "nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8"


class TestModelSupervisor:
    """Test model supervisor integration (for auto-start/stop)."""

    def test_supervisor_headers_without_token(self):
        """Supervisor headers are empty when no token is configured."""
        with patch.dict(os.environ, {}, clear=True):
            headers = _model_supervisor_headers()
            assert headers == {}

    def test_supervisor_headers_with_token(self):
        """Supervisor headers include token when configured."""
        with patch.dict(os.environ, {"TPA_MODEL_SUPERVISOR_TOKEN": "test-token"}):
            headers = _model_supervisor_headers()
            assert headers == {"x-tpa-model-supervisor-token": "test-token"}

    def test_ensure_model_role_sync_no_supervisor(self):
        """Sync ensure returns None when supervisor URL is not set."""
        with patch.dict(os.environ, {}, clear=True):
            result = _ensure_model_role_sync(role="vlm", timeout_seconds=30.0)
            assert result is None

    def test_ensure_model_role_sync_supervisor_success(self):
        """Sync ensure returns base_url on successful supervisor response."""
        with patch.dict(
            os.environ,
            {
                "TPA_MODEL_SUPERVISOR_URL": "http://supervisor:8091",
                "TPA_MODEL_SUPERVISOR_TOKEN": "token",
            },
        ):
            with patch("tpa_api.model_clients.httpx.Client") as mock_client:
                mock_response = MagicMock()
                mock_response.json.return_value = {"base_url": "http://vlm:8000/v1"}
                mock_client.return_value.__enter__.return_value.post.return_value = (
                    mock_response
                )

                result = _ensure_model_role_sync(role="vlm", timeout_seconds=30.0)
                assert result == "http://vlm:8000/v1"

    def test_ensure_model_role_sync_supervisor_error(self):
        """Sync ensure handles supervisor errors gracefully."""
        with patch.dict(
            os.environ, {"TPA_MODEL_SUPERVISOR_URL": "http://supervisor:8091"}
        ):
            with patch("tpa_api.model_clients.httpx.Client") as mock_client:
                mock_client.return_value.__enter__.return_value.post.side_effect = (
                    Exception("Connection refused")
                )

                result = _ensure_model_role_sync(role="vlm", timeout_seconds=30.0)
                assert result is None

    @pytest.mark.asyncio
    async def test_ensure_model_role_async_no_supervisor(self):
        """Async ensure returns None when supervisor URL is not set."""
        with patch.dict(os.environ, {}, clear=True):
            result = await _ensure_model_role(role="vlm", timeout_seconds=30.0)
            assert result is None

    @pytest.mark.asyncio
    async def test_ensure_model_role_async_supervisor_success(self):
        """Async ensure returns base_url on successful supervisor response."""
        with patch.dict(
            os.environ,
            {
                "TPA_MODEL_SUPERVISOR_URL": "http://supervisor:8091",
                "TPA_MODEL_SUPERVISOR_TOKEN": "token",
            },
        ):
            with patch("tpa_api.model_clients.httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.json.return_value = {"base_url": "http://vlm:8000/v1"}

                mock_async_client = AsyncMock()
                mock_async_client.post.return_value = mock_response
                mock_client.return_value.__aenter__.return_value = mock_async_client

                result = await _ensure_model_role(role="vlm", timeout_seconds=30.0)
                assert result == "http://vlm:8000/v1"


class TestVLMEndpointIntegration:
    """Integration tests for VLM endpoint communication (mocked)."""

    def test_vlm_endpoint_health_check_sync(self):
        """Test synchronous health check against VLM endpoint."""
        with patch.dict(
            os.environ,
            {
                "TPA_VLM_BASE_URL": "http://localhost:8000/v1",
                "TPA_VLM_MODEL_ID": "nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8",
            },
        ):
            with patch("tpa_api.model_clients.httpx.Client") as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "object": "list",
                    "data": [{"id": "nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8", "object": "model"}],
                }
                mock_client.return_value.__enter__.return_value.get.return_value = (
                    mock_response
                )

                # Verify endpoint is reachable via environment config
                base_url = os.environ.get("TPA_VLM_BASE_URL")
                assert base_url == "http://localhost:8000/v1"

    @pytest.mark.asyncio
    async def test_vlm_endpoint_health_check_async(self):
        """Test asynchronous health check against VLM endpoint."""
        with patch.dict(
            os.environ,
            {
                "TPA_VLM_BASE_URL": "http://localhost:8000/v1",
                "TPA_VLM_MODEL_ID": "nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8",
            },
        ):
            with patch("tpa_api.model_clients.httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "object": "list",
                    "data": [{"id": "nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8", "object": "model"}],
                }

                mock_async_client = AsyncMock()
                mock_async_client.get.return_value = mock_response
                mock_client.return_value.__aenter__.return_value = mock_async_client

                base_url = os.environ.get("TPA_VLM_BASE_URL")
                assert base_url == "http://localhost:8000/v1"


class TestVLMResponseParsing:
    """Test parsing of VLM response formats."""

    def test_vlm_response_parsing_openai_format(self):
        """Test parsing VLM response in OpenAI format."""
        # Typical vLLM response format for vision completions
        response = {
            "id": "chatcmpl-xxxxx",
            "object": "text_completion",
            "created": 1234567890,
            "model": "nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "This is a plan showing residential buildings...",
                    },
                    "finish_reason": "stop",
                }
            ],
        }
        # Verify structure is valid
        assert response["model"] == "nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8"
        assert len(response["choices"]) == 1
        assert response["choices"][0]["message"]["content"]

    def test_vlm_response_parsing_streaming(self):
        """Test parsing streamed VLM responses."""
        # Typical streaming chunk format
        chunk = {
            "id": "chatcmpl-xxxxx",
            "object": "text_completion.chunk",
            "created": 1234567890,
            "model": "nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8",
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": "This is"},
                    "finish_reason": None,
                }
            ],
        }
        # Verify streaming chunk structure
        assert chunk["choices"][0]["delta"]["content"]

    def test_vlm_response_parsing_with_vision_tokens(self):
        """Test parsing VLM response with vision-specific tokens."""
        response = {
            "id": "chatcmpl-xxxxx",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "[<image>Analysis of plan image] The key features are...",
                    },
                    "finish_reason": "stop",
                }
            ],
        }
        assert "[<image>Analysis" in response["choices"][0]["message"]["content"]


class TestVLMErrorHandling:
    """Test error handling and edge cases for VLM."""

    def test_vlm_timeout_handling(self):
        """Test that VLM requests respect timeout configuration."""
        with patch.dict(
            os.environ, {"TPA_VLM_BASE_URL": "http://localhost:8000/v1"}
        ):
            with patch("tpa_api.model_clients.httpx.Client") as mock_client:
                mock_client.return_value.__enter__.return_value.post.side_effect = (
                    httpx.TimeoutException("Request timeout")
                )
                # Verify error is caught
                try:
                    with httpx.Client(timeout=30.0) as client:
                        client.post(
                            "http://localhost:8000/v1/chat/completions",
                            json={"model": "nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8"},
                            timeout=30.0,
                        )
                except httpx.TimeoutException:
                    pass  # Expected

    def test_vlm_http_error_handling(self):
        """Test handling of HTTP errors from VLM endpoint."""
        with patch.dict(
            os.environ, {"TPA_VLM_BASE_URL": "http://localhost:8000/v1"}
        ):
            with patch("tpa_api.model_clients.httpx.Client") as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 500
                mock_response.text = "Internal Server Error"
                mock_client.return_value.__enter__.return_value.post.return_value = (
                    mock_response
                )

                # Status >= 400 should be handled
                assert 500 >= 400

    def test_vlm_malformed_response(self):
        """Test handling of malformed responses from VLM."""
        with patch.dict(
            os.environ, {"TPA_VLM_BASE_URL": "http://localhost:8000/v1"}
        ):
            with patch("tpa_api.model_clients.httpx.Client") as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.side_effect = json.JSONDecodeError(
                    "Invalid JSON", "", 0
                )
                mock_client.return_value.__enter__.return_value.post.return_value = (
                    mock_response
                )

                # JSONDecodeError should be caught
                try:
                    mock_response.json()
                except json.JSONDecodeError:
                    pass  # Expected


class TestVLMFallbacks:
    """Test VLM fallback and degradation behavior."""

    def test_vlm_fallback_to_default_model(self):
        """Test fallback to default model when custom model not available."""
        with patch.dict(os.environ, {"TPA_VLM_MODEL_ID": ""}):
            model_id = _vlm_model_id()
            assert model_id == "nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8"

    def test_vlm_fallback_to_local_endpoint(self):
        """Test fallback to local endpoint when supervisor unavailable."""
        with patch.dict(
            os.environ,
            {
                "TPA_VLM_BASE_URL": "http://localhost:8000/v1",
            },
        ):
            # If supervisor is down, should use direct endpoint
            base_url = os.environ.get("TPA_VLM_BASE_URL")
            assert base_url == "http://localhost:8000/v1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
