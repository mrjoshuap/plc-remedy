"""Unit tests for PLC client."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from app.plc_client import PLCClient
from app.config import PLCConfig
from app.models import TagResult


@pytest.fixture
def plc_config():
    """Create a test PLC configuration."""
    return PLCConfig(
        ip_address="192.168.1.100",
        slot=0,
        timeout=5.0,
        poll_interval_ms=1000
    )


@pytest.fixture
def plc_client(plc_config):
    """Create a test PLC client."""
    return PLCClient(plc_config)


def test_plc_client_init(plc_client):
    """Test PLC client initialization."""
    assert plc_client.config is not None
    assert not plc_client.is_connected()


@patch('app.plc_client.LogixDriver')
def test_plc_client_connect_success(mock_driver_class, plc_client):
    """Test successful PLC connection."""
    mock_driver = MagicMock()
    mock_driver.connected = True
    mock_driver_class.return_value = mock_driver

    result = plc_client.connect()

    assert result is True
    assert plc_client.is_connected()
    mock_driver.open.assert_called_once()


@patch('app.plc_client.LogixDriver')
def test_plc_client_connect_failure(mock_driver_class, plc_client):
    """Test failed PLC connection."""
    mock_driver = MagicMock()
    mock_driver.connected = False
    mock_driver_class.return_value = mock_driver

    result = plc_client.connect()

    assert result is False
    assert not plc_client.is_connected()


@patch('app.plc_client.LogixDriver')
def test_plc_client_read_tag_success(mock_driver_class, plc_client):
    """Test successful tag read."""
    mock_driver = MagicMock()
    mock_driver.connected = True
    mock_result = MagicMock()
    mock_result.error = None
    mock_result.value = 1750
    mock_driver.read.return_value = mock_result
    mock_driver_class.return_value = mock_driver

    plc_client.connect()
    result = plc_client.read_tag("Motor_Speed")

    assert result.success is True
    assert result.value == 1750
    assert result.error is None


@patch('app.plc_client.LogixDriver')
def test_plc_client_read_tag_error(mock_driver_class, plc_client):
    """Test tag read with error."""
    mock_driver = MagicMock()
    mock_driver.connected = True
    mock_result = MagicMock()
    mock_result.error = "Tag not found"
    mock_result.value = None
    mock_driver.read.return_value = mock_result
    mock_driver_class.return_value = mock_driver

    plc_client.connect()
    result = plc_client.read_tag("InvalidTag")

    assert result.success is False
    assert result.error is not None


def test_plc_client_disconnect(plc_client):
    """Test PLC disconnection."""
    plc_client.disconnect()
    assert not plc_client.is_connected()


def test_plc_client_get_connection_stats(plc_client):
    """Test getting connection statistics."""
    stats = plc_client.get_connection_stats()

    assert stats.connected is False
    assert stats.total_reads == 0
    assert stats.total_errors == 0
