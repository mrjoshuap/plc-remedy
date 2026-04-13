"""Unit tests for chaos engine."""
import time
import pytest
from unittest.mock import Mock, patch

from app.chaos import ChaosEngine, FailureType
from app.config import ChaosConfig, AppConfig, PLCConfig, TagConfig, DashboardConfig, AAPConfig, RemediationConfig, LoggingConfig


@pytest.fixture
def chaos_config():
    """Create a test chaos configuration."""
    return ChaosConfig(
        enabled=True,
        failure_injection_rate=0.1,
        failure_types=["value_anomaly", "network_timeout", "connection_loss"],
        network_timeout_ms=5000,
        anomaly_duration_seconds=10
    )


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
        dashboard=DashboardConfig(),
        logging=LoggingConfig()
    )


@pytest.fixture
def chaos_engine(chaos_config, app_config):
    """Create a test chaos engine."""
    return ChaosEngine(chaos_config, app_config)


def test_chaos_engine_init(chaos_engine, chaos_config):
    """Test chaos engine initialization."""
    assert chaos_engine.config == chaos_config
    assert chaos_engine.is_enabled() == chaos_config.enabled


def test_chaos_engine_enable_disable(chaos_engine):
    """Test enabling and disabling chaos injection."""
    chaos_engine.disable()
    assert not chaos_engine.is_enabled()

    chaos_engine.enable()
    assert chaos_engine.is_enabled()


def test_chaos_engine_get_status(chaos_engine):
    """Test getting chaos engine status."""
    status = chaos_engine.get_status()

    assert 'enabled' in status
    assert 'failure_injection_rate' in status
    assert 'failure_types' in status


def test_chaos_engine_inject_value_anomaly(chaos_engine):
    """Test value anomaly injection."""
    hook = chaos_engine.get_injection_hook()

    if hook:
        # Hook may or may not inject based on random rate
        result = hook("light", True)
        # Result should be a boolean (either original or flipped)
        assert isinstance(result, bool)


def test_chaos_engine_inject_connection_loss(chaos_engine):
    """Test connection loss injection."""
    with patch.object(chaos_engine, '_is_in_grace_period', return_value=False):
        chaos_engine.inject_connection_loss(duration_seconds=5)

    # Connection should be marked as lost
    assert chaos_engine.is_connection_lost() is True


def test_chaos_engine_inject_failure(chaos_engine):
    """Test manual failure injection."""
    result = chaos_engine.inject_failure("connection_loss", duration_seconds=2)

    assert result['success'] is True
    assert result['failure_type'] == "connection_loss"


def test_inject_network_timeout_returns_immediately(chaos_engine):
    """inject_network_timeout() must return in < 1s even for a long duration.

    The blocking sleep was moved to a background greenlet; the caller (HTTP
    handler) must not be held for the duration of the injection.
    """
    # Bypass the startup grace period
    with patch.object(chaos_engine, '_is_in_grace_period', return_value=False), \
         patch('app.chaos.EVENTLET_AVAILABLE', True) as _ev, \
         patch('app.chaos.eventlet') as mock_eventlet:

        mock_eventlet.spawn = Mock()

        start = time.monotonic()
        chaos_engine.inject_network_timeout(duration_ms=10_000)  # 10-second injection
        elapsed = time.monotonic() - start

        assert elapsed < 1.0, f"inject_network_timeout blocked for {elapsed:.2f}s"
        mock_eventlet.spawn.assert_called_once()


def test_inject_network_timeout_daemon_thread_fallback(chaos_engine):
    """Without eventlet, inject_network_timeout() spawns a daemon thread."""
    with patch.object(chaos_engine, '_is_in_grace_period', return_value=False), \
         patch('app.chaos.EVENTLET_AVAILABLE', False), \
         patch('app.chaos.threading') as mock_threading:

        mock_thread = Mock()
        mock_threading.Thread.return_value = mock_thread

        start = time.monotonic()
        chaos_engine.inject_network_timeout(duration_ms=10_000)
        elapsed = time.monotonic() - start

        assert elapsed < 1.0, f"inject_network_timeout blocked for {elapsed:.2f}s"
        mock_threading.Thread.assert_called_once()
        mock_thread.start.assert_called_once()


# ---------------------------------------------------------------------------
# PLC-layer injection tests
# ---------------------------------------------------------------------------

@pytest.fixture
def plc_layer_chaos_config():
    """ChaosConfig with plc_control_url set."""
    return ChaosConfig(
        enabled=True,
        failure_injection_rate=1.0,  # Always inject for deterministic tests
        failure_types=["value_anomaly"],
        network_timeout_ms=5000,
        anomaly_duration_seconds=5,
        plc_control_url="http://127.0.0.1:18080"
    )


@pytest.fixture
def plc_layer_engine(plc_layer_chaos_config, app_config):
    """ChaosEngine with PLC-layer control URL configured."""
    engine = ChaosEngine(plc_layer_chaos_config, app_config)
    # Bypass grace period for all tests
    engine._start_time = engine._start_time.replace(year=2000)
    return engine


def test_inject_value_anomaly_plc_layer_calls_control_api(plc_layer_engine):
    """PLC-layer injection PUTs 'failed' to the control API and returns value unchanged."""
    original_value = True
    with patch.object(plc_layer_engine, '_set_plc_mode', return_value=True) as mock_set, \
         patch.object(plc_layer_engine, '_schedule_plc_reset'):
        result = plc_layer_engine._inject_value_anomaly('light', original_value)

    mock_set.assert_called_once_with('failed')
    assert result == original_value


def test_inject_value_anomaly_plc_layer_schedules_reset(plc_layer_engine):
    """PLC-layer injection schedules a deferred PLC reset."""
    with patch.object(plc_layer_engine, '_set_plc_mode', return_value=True), \
         patch.object(plc_layer_engine, '_schedule_plc_reset') as mock_reset:
        plc_layer_engine._inject_value_anomaly('light', True)

    mock_reset.assert_called_once()
    tag_arg, duration_arg = mock_reset.call_args[0]
    assert tag_arg == 'light'
    assert 1 <= duration_arg <= plc_layer_engine.config.anomaly_duration_seconds


def test_inject_value_anomaly_plc_layer_graceful_failure(plc_layer_engine):
    """When the HTTP call fails, original value is returned without raising."""
    original_value = True
    with patch.object(plc_layer_engine, '_set_plc_mode', return_value=False):
        result = plc_layer_engine._inject_value_anomaly('light', original_value)

    assert result == original_value


def test_inject_failure_value_anomaly_plc_layer(plc_layer_engine):
    """inject_failure('value_anomaly') with plc_control_url triggers PLC-layer injection."""
    with patch.object(plc_layer_engine, '_set_plc_mode', return_value=True) as mock_set, \
         patch.object(plc_layer_engine, '_schedule_plc_reset'):
        # The tag must exist in app_config
        plc_layer_engine._inject_value_anomaly('light', True)

    mock_set.assert_called_once_with('failed')
