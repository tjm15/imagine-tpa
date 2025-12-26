import pytest
from unittest.mock import MagicMock, patch
from tpa_api.providers.docparse_http import HttpDocParseProvider

@pytest.fixture
def mock_httpx():
    with patch("httpx.Client") as mock:
        yield mock

@pytest.fixture
def mock_db():
    with patch("tpa_api.providers.docparse_http._db_execute") as mock:
        yield mock

def test_docparse_success(mock_httpx, mock_db):
    provider = HttpDocParseProvider()
    
    # Mock successful response
    mock_client = MagicMock()
    mock_httpx.return_value.__enter__.return_value = mock_client
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "parse_bundle_path": "bundles/xyz.json",
        "schema_version": "2.0",
        "parse_flags": [],
        "pages": [{"page_number": 1}]
    }
    mock_client.post.return_value = mock_resp
    
    result = provider.parse_document(
        blob_path="raw/123.pdf",
        file_bytes=b"fake-pdf-content",
        filename="doc.pdf",
        options={"run_id": "run-1", "ingest_batch_id": "batch-1"}
    )
    
    assert result["parse_bundle_path"] == "bundles/xyz.json"
    
    # Check that tool_run logging happened (insert into tool_runs)
    mock_db.assert_called()
    call_args = mock_db.call_args[0][0]
    assert "INSERT INTO tool_runs" in call_args
    # Verify page_count was logged in outputs_jsonb
    params = mock_db.call_args[0][1]
    # params structure: (id, name, inputs, outputs, status, start, end, conf, note, run_id, batch_id)
    outputs = params[3] 
    assert outputs['page_count'] == 1

def test_docparse_failure(mock_httpx, mock_db):
    provider = HttpDocParseProvider()
    
    # Mock failure
    mock_client = MagicMock()
    mock_httpx.return_value.__enter__.return_value = mock_client
    mock_client.post.side_effect = Exception("Connection failed")
    
    with pytest.raises(RuntimeError, match="DocParse failed"):
        provider.parse_document(
            blob_path="raw/123.pdf",
            file_bytes=b"fake-pdf-content",
            filename="doc.pdf"
        )
    
    # Check that error was logged
    mock_db.assert_called()
