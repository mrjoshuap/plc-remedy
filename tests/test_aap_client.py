"""Unit tests for AAP client."""
import pytest
from unittest.mock import Mock, patch, MagicMock

from app.aap_client import AAPClient
from app.config import AAPConfig


@pytest.fixture
def aap_config():
    """Create a test AAP configuration (local simulation - no base_url so no real HTTP)."""
    return AAPConfig(
        enabled=True,
        mock_mode=True,
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
    # Configure mock before AAPClient is instantiated so the Session() call gets it
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {'id': 123, 'status': 'pending', 'url': '/api/v2/jobs/123/'}
    mock_response.raise_for_status = MagicMock()
    mock_session.post.return_value = mock_response
    mock_session_class.return_value = mock_session

    aap_config.mock_mode = False
    aap_config.base_url = "https://aap.example.com"
    aap_client = AAPClient(aap_config)

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


def test_poll_job_uses_eventlet_sleep_when_available(aap_client):
    """poll_job_until_complete() must call eventlet.sleep, not time.sleep, under eventlet."""
    finished_status = {'success': True, 'finished': True, 'status': 'successful'}

    with patch('app.aap_client.EVENTLET_AVAILABLE', True), \
         patch('app.aap_client.eventlet') as mock_eventlet, \
         patch.object(aap_client, 'get_job_status', return_value=finished_status):

        aap_client.poll_job_until_complete(999)

        # eventlet.sleep must NOT have been called (job finished on first poll)
        mock_eventlet.sleep.assert_not_called()

    # Now verify it IS called when a second poll is needed
    call_count = 0
    def status_after_one_poll(_job_id):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {'success': True, 'finished': False, 'status': 'running'}
        return finished_status

    with patch('app.aap_client.EVENTLET_AVAILABLE', True), \
         patch('app.aap_client.eventlet') as mock_eventlet, \
         patch.object(aap_client, 'get_job_status', side_effect=status_after_one_poll):

        aap_client.poll_job_until_complete(999)

        mock_eventlet.sleep.assert_called_once()


def test_poll_job_falls_back_to_time_sleep_without_eventlet(aap_client):
    """poll_job_until_complete() falls back to time.sleep when eventlet is unavailable."""
    call_count = 0
    finished = {'success': True, 'finished': True, 'status': 'successful'}

    def status_side_effect(_job_id):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {'success': True, 'finished': False, 'status': 'running'}
        return finished

    with patch('app.aap_client.EVENTLET_AVAILABLE', False), \
         patch('app.aap_client.time.sleep') as mock_sleep, \
         patch.object(aap_client, 'get_job_status', side_effect=status_side_effect):

        aap_client.poll_job_until_complete(999)

        mock_sleep.assert_called_once()
