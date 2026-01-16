"""Unit tests for chaos engine."""
import pytest
from unittest.mock import Mock

from app.chaos import ChaosEngine, FailureType
from app.config import ChaosConfig, AppConfig, PLCConfig, TagConfig, DashboardConfig, AAPConfig, RemediationConfig


@pytest.fixture
def chaos_config():
    """Create a test chaos configuration."""
    return ChaosConfig(
        enabled=True,
        failure_injection_rate=0.1,
        failure_types=["value_anomaly", "network_timeout"],
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
        dashboard=DashboardConfig()
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
    chaos_engine.inject_connection_loss(duration_seconds=5)
    
    # Connection should be marked as lost
    assert chaos_engine.is_connection_lost() is True


def test_chaos_engine_inject_failure(chaos_engine):
    """Test manual failure injection."""
    result = chaos_engine.inject_failure("connection_loss", duration_seconds=2)
    
    assert result['success'] is True
    assert result['failure_type'] == "connection_loss"
