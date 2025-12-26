import pytest
from unittest.mock import MagicMock, patch
from tpa_api.providers.oss_blob import MinIOBlobStoreProvider

@pytest.fixture
def mock_minio():
    with patch("tpa_api.providers.oss_blob.minio_client_or_none") as mock:
        client = MagicMock()
        mock.return_value = client
        yield client

@pytest.fixture
def mock_db():
    with patch("tpa_api.providers.oss_blob._db_execute") as mock:
        yield mock

def test_oss_blob_put(mock_minio, mock_db):
    provider = MinIOBlobStoreProvider(bucket="test-bucket")
    
    mock_minio.bucket_exists.return_value = True
    mock_minio.put_object.return_value = MagicMock(etag="test-etag")
    
    result = provider.put_blob("test/path.pdf", b"test data", content_type="application/pdf")
    
    assert result["path"] == "test/path.pdf"
    assert result["etag"] == "test-etag"
    assert result["size_bytes"] == 9
    
    mock_minio.put_object.assert_called_once()
    mock_db.assert_called_once() # tool_run log

def test_oss_blob_get(mock_minio, mock_db):
    provider = MinIOBlobStoreProvider(bucket="test-bucket")
    
    mock_resp = MagicMock()
    mock_resp.read.return_value = b"test data"
    mock_resp.headers = {"content-type": "application/pdf"}
    mock_minio.get_object.return_value = mock_resp
    
    result = provider.get_blob("test/path.pdf")
    
    assert result["bytes"] == b"test data"
    assert result["content_type"] == "application/pdf"
    
    mock_minio.get_object.assert_called_once()
    mock_db.assert_called_once()

def test_oss_blob_exists(mock_minio):
    provider = MinIOBlobStoreProvider(bucket="test-bucket")
    
    mock_minio.stat_object.return_value = MagicMock()
    assert provider.exists("test/path.pdf") is True
    
    mock_minio.stat_object.side_effect = Exception("Not found")
    assert provider.exists("nonexistent.pdf") is False
