"""Chaos engineering engine for failure injection."""
import logging
import random
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable
from enum import Enum

from app.config import ChaosConfig, TagConfig, AppConfig
from app.models import EventType, Severity

logger = logging.getLogger(__name__)

# Startup grace period - no chaos injection for this duration after initialization
STARTUP_GRACE_PERIOD_SECONDS = 10

# Per-tag injection cooldown - minimum time between injections for the same tag
TAG_INJECTION_COOLDOWN_SECONDS = 5


class FailureType(Enum):
    """Types of failures that can be injected."""
    VALUE_ANOMALY = "value_anomaly"
    NETWORK_TIMEOUT = "network_timeout"
    CONNECTION_LOSS = "connection_loss"
    SERVICE_CRASH = "service_crash"


class ChaosEngine:
    """Engine for injecting failures into the system for testing."""

    def __init__(self, config: ChaosConfig, app_config: AppConfig):
        """Initialize chaos engine.

        Args:
            config: Chaos configuration
            app_config: Full application configuration (for tag info)
        """
        self.config = config
        self.app_config = app_config
        self._enabled = config.enabled
        self._lock = threading.Lock()

        # Track startup time for grace period
        self._start_time = datetime.now()

        # Track injected failures
        self._injection_history: list = []
        self._active_injections: Dict[str, Dict[str, Any]] = {}

        # Track active value anomalies per tag (with expiration times)
        self._active_value_anomalies: Dict[str, Dict[str, Any]] = {}

        # Track last injection time per tag for cooldown
        self._last_injection_time: Dict[str, datetime] = {}

        # Connection loss simulation
        self._connection_lost = False
        self._connection_loss_end_time: Optional[datetime] = None

    def is_enabled(self) -> bool:
        """Check if chaos injection is enabled.

        Returns:
            True if enabled, False otherwise
        """
        return self._enabled

    def _is_in_grace_period(self) -> bool:
        """Check if currently in startup grace period.

        Returns:
            True if within grace period, False otherwise
        """
        elapsed = (datetime.now() - self._start_time).total_seconds()
        return elapsed < STARTUP_GRACE_PERIOD_SECONDS

    def _get_grace_period_remaining(self) -> float:
        """Get remaining time in grace period.

        Returns:
            Remaining seconds in grace period (0 if grace period has passed)
        """
        elapsed = (datetime.now() - self._start_time).total_seconds()
        remaining = STARTUP_GRACE_PERIOD_SECONDS - elapsed
        return max(0.0, remaining)

    def _is_tag_in_cooldown(self, tag_name: str) -> bool:
        """Check if a tag is currently in cooldown period.

        Args:
            tag_name: Name of the tag to check

        Returns:
            True if tag is in cooldown, False otherwise
        """
        if tag_name not in self._last_injection_time:
            return False

        last_injection = self._last_injection_time[tag_name]
        elapsed = (datetime.now() - last_injection).total_seconds()
        return elapsed < TAG_INJECTION_COOLDOWN_SECONDS

    def enable(self) -> None:
        """Enable chaos injection."""
        with self._lock:
            self._enabled = True
            logger.info("Chaos injection enabled")

    def disable(self) -> None:
        """Disable chaos injection."""
        with self._lock:
            self._enabled = False
            # Clear active injections
            self._active_injections.clear()
            self._active_value_anomalies.clear()
            self._last_injection_time.clear()
            self._connection_lost = False
            logger.info("Chaos injection disabled")

    def get_injection_hook(self) -> Optional[Callable[[str, Any], Any]]:
        """Get the injection hook function for the monitor.

        Returns:
            Hook function or None if disabled
        """
        if not self._enabled:
            return None

        return self._inject_value_anomaly

    def _inject_value_anomaly(self, tag_name: str, value: Any) -> Any:
        """Inject value anomaly into tag read.

        Args:
            tag_name: Name of the tag
            value: Original value

        Returns:
            Modified value or original if no injection
        """
        if not self._enabled:
            return value

        # Check startup grace period
        if self._is_in_grace_period():
            return value

        with self._lock:
            # Check for existing active anomaly
            if tag_name in self._active_value_anomalies:
                anomaly = self._active_value_anomalies[tag_name]
                if datetime.now() < anomaly['end_time']:
                    # Still active, return injected value
                    return anomaly['injected_value']
                else:
                    # Expired, remove and return original
                    del self._active_value_anomalies[tag_name]
                    logger.info(f"Chaos: Value anomaly expired for {tag_name}, returning to normal")
                    # Continue to check cooldown even after anomaly expires

        # Check cooldown period (after active anomaly check)
        if self._is_tag_in_cooldown(tag_name):
            return value

        # No active anomaly and not in cooldown, check if we should inject
        if random.random() > self.config.failure_injection_rate:
            return value

        # Check if this failure type is enabled
        if FailureType.VALUE_ANOMALY.value not in self.config.failure_types:
            return value

        # Get tag config to determine appropriate anomaly
        if tag_name not in self.app_config.tags:
            return value

        tag_config = self.app_config.tags[tag_name]

        # Inject anomaly based on tag type
        if tag_config.type == 'bool':
            # Flip boolean value
            injected_value = not value
        elif tag_config.type == 'int':
            # Inject value outside normal range
            if tag_config.failure_threshold_low is not None:
                injected_value = int(tag_config.failure_threshold_low - 100)
            elif tag_config.failure_threshold_high is not None:
                injected_value = int(tag_config.failure_threshold_high + 100)
            else:
                injected_value = value * 2  # Double the value
        elif tag_config.type == 'float':
            # Similar to int
            if tag_config.failure_threshold_low is not None:
                injected_value = float(tag_config.failure_threshold_low - 100.0)
            elif tag_config.failure_threshold_high is not None:
                injected_value = float(tag_config.failure_threshold_high + 100.0)
            else:
                injected_value = value * 2.0
        else:
            injected_value = value

        # Generate random duration (1-180 seconds) and store active anomaly
        duration = random.randint(1, 180)
        end_time = datetime.now() + timedelta(seconds=duration)

        # Log injection
        injection_id = f"{tag_name}_{int(time.time() * 1000)}"
        with self._lock:
            # Double-check if another thread injected an anomaly while we were calculating
            if tag_name in self._active_value_anomalies:
                anomaly = self._active_value_anomalies[tag_name]
                if datetime.now() < anomaly['end_time']:
                    # Another thread already injected, use that value
                    return anomaly['injected_value']
                else:
                    # Previous anomaly expired, remove it
                    del self._active_value_anomalies[tag_name]

            self._injection_history.append({
                'id': injection_id,
                'tag_name': tag_name,
                'failure_type': FailureType.VALUE_ANOMALY.value,
                'original_value': value,
                'injected_value': injected_value,
                'timestamp': datetime.now().isoformat()
            })

            # Store active anomaly with expiration
            self._active_value_anomalies[tag_name] = {
                'injected_value': injected_value,
                'original_value': value,
                'end_time': end_time,
                'duration_seconds': duration
            }

            # Update last injection time for cooldown tracking
            self._last_injection_time[tag_name] = datetime.now()

        logger.warning(f"Chaos: Injected value anomaly for {tag_name}: {value} -> {injected_value} (duration: {duration}s)")

        return injected_value

    def inject_network_timeout(self, duration_ms: Optional[int] = None) -> None:
        """Inject network timeout.

        Args:
            duration_ms: Duration of timeout in milliseconds
        """
        # Check startup grace period
        if self._is_in_grace_period():
            remaining = self._get_grace_period_remaining()
            logger.info(f"Chaos injection skipped: startup grace period active ({remaining:.1f}s remaining)")
            return

        if FailureType.NETWORK_TIMEOUT.value not in self.config.failure_types:
            logger.warning("Network timeout injection not enabled in config")
            return

        duration = duration_ms or self.config.network_timeout_ms

        injection_id = f"timeout_{int(time.time() * 1000)}"
        with self._lock:
            self._active_injections[injection_id] = {
                'failure_type': FailureType.NETWORK_TIMEOUT.value,
                'duration_ms': duration,
                'start_time': datetime.now(),
                'end_time': datetime.now() + timedelta(milliseconds=duration)
            }

        logger.warning(f"Chaos: Injected network timeout for {duration}ms")

        # Sleep to simulate timeout (in a real implementation, this would
        # be handled differently - perhaps by modifying the PLC client)
        time.sleep(duration / 1000.0)

        with self._lock:
            if injection_id in self._active_injections:
                del self._active_injections[injection_id]

    def inject_connection_loss(self, duration_seconds: Optional[int] = None) -> None:
        """Inject connection loss.

        Args:
            duration_seconds: Duration of connection loss in seconds
        """
        # Check startup grace period
        if self._is_in_grace_period():
            remaining = self._get_grace_period_remaining()
            logger.info(f"Chaos injection skipped: startup grace period active ({remaining:.1f}s remaining)")
            return

        if FailureType.CONNECTION_LOSS.value not in self.config.failure_types:
            logger.warning("Connection loss injection not enabled in config")
            return

        duration = duration_seconds or self.config.anomaly_duration_seconds

        with self._lock:
            self._connection_lost = True
            self._connection_loss_end_time = datetime.now() + timedelta(seconds=duration)

        injection_id = f"connection_loss_{int(time.time() * 1000)}"
        with self._lock:
            self._active_injections[injection_id] = {
                'failure_type': FailureType.CONNECTION_LOSS.value,
                'duration_seconds': duration,
                'start_time': datetime.now(),
                'end_time': self._connection_loss_end_time
            }

        logger.warning(f"Chaos: Injected connection loss for {duration} seconds")

        # Schedule restoration
        def restore_connection():
            time.sleep(duration)
            with self._lock:
                self._connection_lost = False
                self._connection_loss_end_time = None
                if injection_id in self._active_injections:
                    del self._active_injections[injection_id]
            logger.info("Chaos: Connection loss restored")

        threading.Thread(target=restore_connection, daemon=True).start()

    def is_connection_lost(self) -> bool:
        """Check if connection loss is currently active.

        Returns:
            True if connection is simulated as lost
        """
        with self._lock:
            if self._connection_lost and self._connection_loss_end_time:
                if datetime.now() >= self._connection_loss_end_time:
                    # Time expired, restore connection
                    self._connection_lost = False
                    self._connection_loss_end_time = None
                    return False
                return True
            return False

    def inject_service_crash(self) -> None:
        """Inject service crash (raises exception).

        Note: This will actually crash the service, use with caution!
        """
        if FailureType.SERVICE_CRASH.value not in self.config.failure_types:
            logger.warning("Service crash injection not enabled in config")
            return

        logger.critical("Chaos: Injecting service crash!")
        raise RuntimeError("Chaos engineering: Service crash injection")

    def inject_failure(self, failure_type: str, **kwargs) -> Dict[str, Any]:
        """Manually inject a specific failure type.

        Args:
            failure_type: Type of failure to inject
            **kwargs: Additional parameters for the failure type

        Returns:
            Dictionary with injection information
        """
        if failure_type == FailureType.VALUE_ANOMALY.value:
            # Value anomaly is handled via the hook, can't be manually triggered
            return {
                'success': False,
                'error': 'Value anomaly injection is automatic based on injection rate'
            }

        elif failure_type == FailureType.NETWORK_TIMEOUT.value:
            duration_ms = kwargs.get('duration_ms', self.config.network_timeout_ms)
            self.inject_network_timeout(duration_ms)
            return {
                'success': True,
                'failure_type': failure_type,
                'duration_ms': duration_ms
            }

        elif failure_type == FailureType.CONNECTION_LOSS.value:
            duration_seconds = kwargs.get('duration_seconds', self.config.anomaly_duration_seconds)
            self.inject_connection_loss(duration_seconds)
            return {
                'success': True,
                'failure_type': failure_type,
                'duration_seconds': duration_seconds
            }

        elif failure_type == FailureType.SERVICE_CRASH.value:
            # This will actually crash, so we return info but don't call it
            return {
                'success': False,
                'error': 'Service crash injection will terminate the service. Use with extreme caution!'
            }

        else:
            return {
                'success': False,
                'error': f'Unknown failure type: {failure_type}'
            }

    def get_status(self) -> Dict[str, Any]:
        """Get chaos engine status.

        Returns:
            Dictionary with current status
        """
        with self._lock:
            in_grace_period = self._is_in_grace_period()
            grace_period_remaining = self._get_grace_period_remaining()

            # Clean up old cooldown entries (older than 1 hour)
            now = datetime.now()
            tags_to_remove = [
                tag for tag, last_time in self._last_injection_time.items()
                if (now - last_time).total_seconds() > 3600
            ]
            for tag in tags_to_remove:
                del self._last_injection_time[tag]

            return {
                'enabled': self._enabled,
                'failure_injection_rate': self.config.failure_injection_rate,
                'failure_types': self.config.failure_types,
                'active_injections': len(self._active_injections),
                'active_value_anomalies': len(self._active_value_anomalies),
                'connection_lost': self._connection_lost,
                'total_injections': len(self._injection_history),
                'recent_injections': self._injection_history[-10:] if self._injection_history else [],
                'in_grace_period': in_grace_period,
                'grace_period_remaining_seconds': round(grace_period_remaining, 1) if in_grace_period else 0.0,
                'tags_in_cooldown': len([tag for tag in self._last_injection_time.keys() if self._is_tag_in_cooldown(tag)])
            }
