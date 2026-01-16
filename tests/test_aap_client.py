"""Unit tests for AAP client."""
import pytest
from unittest.mock import Mock, patch, MagicMock

from app.aap_client import AAPClient
from app.config import AAPConfig


@pytest.fixture
def aap_config():
    """Create a test AAP configuration."""
    return AAPConfig(
        enabled=True,
        mock_mode=True,
        base_url="https://aap.example.com",
        verify_ssl=True,
        token="test-token",
        job_templates={
            "emergency_stop": 42,
            "emergency_reset": 43
        }
    )


@pytest.fixture
def aap_client(aap_config):
    """Create a test AAP client."""
    return AAPClient(aap_config)


def test_aap_client_init(aap_client, aap_config):
    """Test AAP client initialization."""
    assert aap_client.config == aap_config


def test_aap_client_launch_mock_job(aap_client):
    """Test launching a mock job."""
    result = aap_client.launch_job(42)
    
    assert result['success'] is True
    assert 'job_id' in result
    assert result['status'] == 'pending'


@patch('app.aap_client.requests.Session')
def test_aap_client_launch_real_job(mock_session_class, aap_config):
    """Test launching a real AAP job."""
    aap_config.mock_mode = False
    aap_client = AAPClient(aap_config)
    
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {'id': 123, 'status': 'pending', 'url': '/api/v2/jobs/123/'}
    mock_response.raise_for_status = MagicMock()
    mock_session.post.return_value = mock_response
    mock_session_class.return_value = mock_session
    
    result = aap_client.launch_job(42)
    
    assert result['success'] is True
    assert result['job_id'] == 123


def test_aap_client_get_mock_job_status(aap_client):
    """Test getting mock job status."""
    result = aap_client.get_job_status(12345)
    
    assert result['success'] is True
    assert 'status' in result
    assert 'finished' in result


def test_aap_client_get_mock_job_output(aap_client):
    """Test getting mock job output."""
    output = aap_client.get_job_output(12345)
    
    assert isinstance(output, str)
    assert "Mock AAP Job Output" in output
