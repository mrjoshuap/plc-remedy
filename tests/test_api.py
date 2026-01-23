"""Unit tests for REST API."""
import pytest
from unittest.mock import Mock, MagicMock, patch
from flask import Flask

from app.api.routes import api, init_api
from app.config import AppConfig, PLCConfig, TagConfig, DashboardConfig, AAPConfig, RemediationConfig, ChaosConfig
from app.monitor import MonitorService
from app.aap_client import AAPClient
from app.chaos import ChaosEngine
from app.plc_client import PLCClient
from flask_socketio import SocketIO


@pytest.fixture
def app_config():
    """Create a test application configuration."""
    return AppConfig(
        plc=PLCConfig(ip_address="192.168.1.100"),
        tags={
            "light": TagConfig(
                name="Light_Status",
                type="bool",
                nominal=True,
                failure_condition="equals",
                failure_value=False
            )
        },
        aap=AAPConfig(),
        remediation=RemediationConfig(),
        chaos=ChaosConfig(),
        dashboard=DashboardConfig()
    )


@pytest.fixture
def mock_components(app_config):
    """Create mock components for API testing."""
    mock_plc = MagicMock(spec=PLCClient)
    mock_aap = MagicMock(spec=AAPClient)
    mock_monitor = MagicMock(spec=MonitorService)
    mock_chaos = MagicMock(spec=ChaosEngine)
    mock_socketio = MagicMock(spec=SocketIO)

    return {
        'monitor': mock_monitor,
        'aap': mock_aap,
        'chaos': mock_chaos,
        'config': app_config,
        'socketio': mock_socketio
    }


@pytest.fixture
def test_app(mock_components):
    """Create a test Flask application."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'

    # Initialize API
    init_api(
        mock_components['monitor'],
        mock_components['aap'],
        mock_components['chaos'],
        mock_components['config'],
        mock_components['socketio']
    )

    app.register_blueprint(api)

    return app


@pytest.fixture
def client(test_app):
    """Create a test client."""
    return test_app.test_client()


def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get('/api/v1/health')

    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True


def test_status_endpoint(client, mock_components):
    """Test status endpoint."""
    mock_components['monitor'].plc_client.is_connected.return_value = True
    mock_components['monitor'].plc_client.get_connection_stats.return_value = Mock(
        connected=True,
        to_dict=lambda: {'connected': True}
    )
    mock_components['monitor'].get_current_values.return_value = {}

    response = client.get('/api/v1/status')

    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True


def test_tags_endpoint(client, mock_components):
    """Test tags endpoint."""
    mock_components['monitor'].get_current_values.return_value = {}

    response = client.get('/api/v1/tags')

    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True


def test_chaos_status_endpoint(client, mock_components):
    """Test chaos status endpoint."""
    mock_components['chaos'].get_status.return_value = {
        'enabled': False,
        'failure_injection_rate': 0.05
    }

    response = client.get('/api/v1/chaos/status')

    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True


def test_chaos_enable_endpoint(client, mock_components):
    """Test chaos enable endpoint."""
    response = client.post('/api/v1/chaos/enable')

    assert response.status_code == 200
    mock_components['chaos'].enable.assert_called_once()


def test_config_endpoint(client):
    """Test config endpoint."""
    response = client.get('/api/v1/config')

    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert 'data' in data
