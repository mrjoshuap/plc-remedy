"""Unit tests for monitor service."""
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from app.monitor import MonitorService
from app.config import AppConfig, PLCConfig, TagConfig, DashboardConfig, AAPConfig, RemediationConfig, ChaosConfig, LoggingConfig
from app.plc_client import PLCClient
from app.models import EventType


@pytest.fixture
def app_config():
    """Create a test application configuration."""
    return AppConfig(
        plc=PLCConfig(ip_address="192.168.1.100", slot=0, timeout=5.0, poll_interval_ms=1000),
        tags={
            "light": TagConfig(
                name="Light_Status",
                type="bool",
                nominal=True,
                failure_condition="equals",
                failure_value=False
            ),
            "motor_speed": TagConfig(
                name="Motor_Speed",
                type="int",
                nominal=1750,
                failure_condition="outside_range",
                failure_threshold_low=1500,
                failure_threshold_high=2000
            )
        },
        aap=AAPConfig(),
        remediation=RemediationConfig(),
        chaos=ChaosConfig(),
        dashboard=DashboardConfig(),
        logging=LoggingConfig()
    )


@pytest.fixture
def mock_plc_client():
    """Create a mock PLC client."""
    client = MagicMock(spec=PLCClient)
    client.is_connected.return_value = True
    client.read_tags.return_value = {
        "Light_Status": Mock(success=True, value=True, timestamp=datetime.now(), error=None),
        "Motor_Speed": Mock(success=True, value=1750, timestamp=datetime.now(), error=None)
    }
    client.get_connection_stats.return_value = Mock(
        connected=True,
        last_successful_read=datetime.now(),
        total_reads=100,
        total_errors=0,
        connection_start_time=datetime.now(),
        last_error=None,
        to_dict=lambda: {}
    )
    return client


@pytest.fixture
def monitor_service(app_config, mock_plc_client):
    """Create a test monitor service."""
    return MonitorService(app_config, mock_plc_client, socketio=None)


def test_monitor_service_init(monitor_service):
    """Test monitor service initialization."""
    assert monitor_service.config is not None
    assert not monitor_service._running


def test_monitor_service_start_stop(monitor_service):
    """Test starting and stopping monitor service."""
    monitor_service.start()
    assert monitor_service._running is True

    monitor_service.stop()
    assert monitor_service._running is False


def test_monitor_service_evaluate_threshold_violation(monitor_service):
    """Test threshold violation detection."""
    # Test outside_range violation
    monitor_service._evaluate_threshold("motor_speed", 2500, datetime.now())

    violations = monitor_service.get_active_violations()
    assert len(violations) > 0
    assert violations[0].tag_name == "motor_speed"


def test_monitor_service_evaluate_threshold_normal(monitor_service):
    """Test normal value (no violation)."""
    monitor_service._evaluate_threshold("motor_speed", 1750, datetime.now())

    violations = monitor_service.get_active_violations()
    assert len(violations) == 0


def test_monitor_service_get_current_values(monitor_service, mock_plc_client):
    """Test getting current tag values."""
    values = monitor_service.get_current_values()

    # Values should be empty initially, but method should work
    assert isinstance(values, dict)


def test_monitor_service_get_statistics(monitor_service):
    """Test getting monitoring statistics."""
    stats = monitor_service.get_statistics()

    assert 'uptime_seconds' in stats
    assert 'total_tag_reads' in stats
    assert 'total_violations' in stats


def test_violation_resolution_emits_without_deadlock(app_config, mock_plc_client):
    """Resolution path should emit outside lock and not deadlock."""
    socketio = Mock()
    monitor = MonitorService(app_config, mock_plc_client, socketio=socketio)

    # Create an active violation first.
    monitor._evaluate_threshold("motor_speed", 2500, datetime.now())
    assert "motor_speed" in monitor._active_violations

    # Feed enough normal readings to resolve the violation.
    monitor._evaluate_threshold("motor_speed", 1750, datetime.now())
    monitor._evaluate_threshold("motor_speed", 1750, datetime.now())
    monitor._evaluate_threshold("motor_speed", 1750, datetime.now())

    # Violation should be resolved and event emission should have occurred.
    assert monitor._active_violations["motor_speed"].resolved is True
    assert socketio.emit.called
    emitted_event_names = [call.args[0] for call in socketio.emit.call_args_list]
    assert EventType.THRESHOLD_VIOLATION.value in emitted_event_names


def test_poll_cycle_continues_after_violation_resolution(app_config):
    """Poll cycles should continue appending history after recovery."""
    socketio = Mock()
    client = MagicMock(spec=PLCClient)
    client.is_connected.return_value = True
    client.check_connection_health.return_value = True
    client.connect.return_value = True
    client.disconnect.return_value = None
    client.get_connection_stats.return_value = Mock(
        connected=True,
        last_successful_read=datetime.now(),
        total_reads=0,
        total_errors=0,
        connection_start_time=datetime.now(),
        last_error=None,
        to_dict=lambda: {}
    )

    # Sequence: fail speed once -> then three normal readings (resolution) -> keep normal
    read_sequence = [
        {
            "Light_Status": Mock(success=True, value=True, timestamp=datetime.now(), error=None),
            "Motor_Speed": Mock(success=True, value=2500, timestamp=datetime.now(), error=None),
        },
        {
            "Light_Status": Mock(success=True, value=True, timestamp=datetime.now(), error=None),
            "Motor_Speed": Mock(success=True, value=1750, timestamp=datetime.now(), error=None),
        },
        {
            "Light_Status": Mock(success=True, value=True, timestamp=datetime.now(), error=None),
            "Motor_Speed": Mock(success=True, value=1750, timestamp=datetime.now(), error=None),
        },
        {
            "Light_Status": Mock(success=True, value=True, timestamp=datetime.now(), error=None),
            "Motor_Speed": Mock(success=True, value=1750, timestamp=datetime.now(), error=None),
        },
        {
            "Light_Status": Mock(success=True, value=True, timestamp=datetime.now(), error=None),
            "Motor_Speed": Mock(success=True, value=1755, timestamp=datetime.now(), error=None),
        },
        {
            "Light_Status": Mock(success=True, value=True, timestamp=datetime.now(), error=None),
            "Motor_Speed": Mock(success=True, value=1748, timestamp=datetime.now(), error=None),
        },
    ]
    client.read_tags.side_effect = read_sequence

    monitor = MonitorService(app_config, client, socketio=socketio)

    for _ in range(len(read_sequence)):
        monitor._poll_cycle()

    # Ensure polling continued after resolution and history kept growing.
    speed_history = monitor.get_tag_history("motor_speed")
    assert len(speed_history) == len(read_sequence)
    assert speed_history[-1]["value"] == 1748
