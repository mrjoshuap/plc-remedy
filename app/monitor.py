"""Monitor service for continuous PLC polling and threshold detection."""
import logging
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from flask_socketio import SocketIO

# Import eventlet for non-blocking sleep when using eventlet async mode
try:
    import eventlet
    EVENTLET_AVAILABLE = True
except ImportError:
    EVENTLET_AVAILABLE = False

from app.config import AppConfig, TagConfig
from app.models import (
    TagResult, Event, EventType, Severity, ThresholdViolation
)
from app.plc_client import PLCClient

logger = logging.getLogger(__name__)


class MonitorService:
    """Service for monitoring PLC tags and detecting threshold violations."""
    
    def __init__(self, config: AppConfig, plc_client: PLCClient, socketio: Optional[SocketIO] = None):
        """Initialize monitor service.
        
        Args:
            config: Application configuration
            plc_client: PLC client instance
            socketio: Flask-SocketIO instance for real-time events
        """
        self.config = config
        self.plc_client = plc_client
        self.socketio = socketio
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # Tag history storage (circular buffer)
        self._tag_history: Dict[str, deque] = {}
        max_history = config.dashboard.chart_data_points
        for tag_name in config.tags.keys():
            self._tag_history[tag_name] = deque(maxlen=max_history)
        
        # Event storage (circular buffer)
        self._events: deque = deque(maxlen=1000)
        
        # Active violations tracking
        self._active_violations: Dict[str, ThresholdViolation] = {}
        
        # Current tag values
        self._current_values: Dict[str, TagResult] = {}
        
        # Statistics
        self._start_time = datetime.now()
        self._total_reads = 0
        self._total_violations = 0
        self._last_connection_state = False
        
        # Chaos injection hook (set by chaos engine)
        self._chaos_hook: Optional[Callable[[str, Any], Any]] = None
        
        # Remediation trigger hook (set by app initialization)
        self._remediation_hook: Optional[Callable[[str], None]] = None
    
    def set_chaos_hook(self, hook: Callable[[str, Any], Any]) -> None:
        """Set chaos injection hook.
        
        Args:
            hook: Function that takes (tag_name, value) and returns modified value
        """
        self._chaos_hook = hook
    
    def set_remediation_hook(self, hook: Callable[[str], None]) -> None:
        """Set remediation trigger hook.
        
        Args:
            hook: Function that takes action type (str) and triggers remediation
        """
        self._remediation_hook = hook
        logger.info("Remediation hook set successfully for auto-remediation")
    
    def start(self) -> None:
        """Start the monitoring thread."""
        if self._running:
            logger.warning("Monitor service already running")
            return
        
        self._running = True
        
        # Emit initial connection state (check outside any locks)
        initial_connected = self.plc_client.is_connected()
        with self._lock:
            self._last_connection_state = initial_connected
        if initial_connected:
            self._emit_event(EventType.CONNECTION_RESTORED, {
                'message': 'PLC connection established'
            }, Severity.INFO)
        else:
            self._emit_event(EventType.CONNECTION_LOST, {
                'message': 'PLC connection not available'
            }, Severity.ERROR)
        
        # Use eventlet greenlet instead of regular thread when eventlet is available
        # This prevents lock contention between regular threads and eventlet greenlets
        if EVENTLET_AVAILABLE:
            self._thread = eventlet.spawn(self._monitor_loop)
            logger.info("Monitor service started (using eventlet greenlet)")
        else:
            self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._thread.start()
            logger.info("Monitor service started (using regular thread)")
    
    def stop(self) -> None:
        """Stop the monitoring thread."""
        if not self._running:
            return
        
        self._running = False
        if self._thread:
            if EVENTLET_AVAILABLE and hasattr(self._thread, 'kill'):
                # eventlet greenlet
                try:
                    self._thread.kill()
                except Exception:
                    pass
            else:
                # regular thread
                self._thread.join(timeout=5.0)
        logger.info("Monitor service stopped")
    
    def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        poll_interval = self.config.plc.poll_interval_ms / 1000.0
        
        while self._running:
            try:
                self._poll_cycle()
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}", exc_info=True)
            
            # Sleep until next poll
            # Use eventlet.sleep if available to avoid blocking HTTP requests
            if EVENTLET_AVAILABLE:
                eventlet.sleep(poll_interval)
            else:
                time.sleep(poll_interval)
    
    def _poll_cycle(self) -> None:
        """Execute one polling cycle."""
        # Get actual PLC tag names from config (not the config keys)
        tag_mapping = {}  # Maps config key -> actual PLC tag name
        tag_names = []  # List of actual PLC tag names to read
        for config_key, tag_config in self.config.tags.items():
            actual_tag_name = tag_config.name  # Use the 'name' field from config
            tag_mapping[actual_tag_name] = config_key  # Reverse mapping for results
            tag_names.append(actual_tag_name)
        
        # Read all tags using actual PLC tag names (OUTSIDE the lock to avoid blocking API requests)
        results = self.plc_client.read_tags(tag_names)
        logger.debug(f"Read tags results: {[(k, v.success, v.value if v.success else v.error) for k, v in results.items()]}")
        
        # Map results back to config keys for internal storage
        mapped_results = {}
        for actual_tag_name, result in results.items():
            config_key = tag_mapping.get(actual_tag_name, actual_tag_name)
            mapped_results[config_key] = result
        results = mapped_results
        logger.debug(f"Mapped results to config keys: {list(results.keys())}")
        
        # Prepare events to emit (outside lock)
        events_to_emit = []
        
        # Prepare data outside lock
        values_to_store = {}
        history_entries = {}
        threshold_evaluations = []
        
        for tag_name, result in results.items():
            try:
                logger.debug(f"Processing tag {tag_name}, success={result.success}, value={result.value if result.success else result.error}")
                values_to_store[tag_name] = result
                
                if result.success:
                    # Prepare history entry
                    history_entries[tag_name] = {
                        'timestamp': result.timestamp.isoformat(),
                        'value': result.value
                    }
                    
                    # Apply chaos injection if enabled
                    value = result.value
                    if self._chaos_hook:
                        try:
                            value = self._chaos_hook(tag_name, value)
                        except Exception as e:
                            logger.warning(f"Chaos hook error for {tag_name}: {e}")
                    
                    # Prepare threshold evaluation (will do outside lock)
                    threshold_evaluations.append((tag_name, value, result.timestamp))
                    
                    # Queue event to emit
                    events_to_emit.append((EventType.TAG_READ, {
                        'tag_name': tag_name,
                        'value': value,
                        'success': True
                    }, Severity.INFO, tag_name))
                else:
                    # Queue error event
                    logger.debug(f"Tag {tag_name} read failed: {result.error}")
                    events_to_emit.append((EventType.TAG_READ, {
                        'tag_name': tag_name,
                        'error': result.error
                    }, Severity.ERROR, tag_name))
            except Exception as e:
                logger.error(f"Error processing tag {tag_name}: {e}", exc_info=True)
        
        # Update shared state quickly inside lock (minimize lock time)
        with self._lock:
            for tag_name, result in values_to_store.items():
                self._current_values[tag_name] = result
                self._total_reads += 1
            
            for tag_name, history_entry in history_entries.items():
                self._tag_history[tag_name].append(history_entry)
        
        # Evaluate thresholds OUTSIDE the lock (they will acquire lock internally if needed)
        for tag_name, value, timestamp in threshold_evaluations:
            self._evaluate_threshold(tag_name, value, timestamp)
        
        # Check connection state changes OUTSIDE the lock to avoid blocking eventlet
        current_connected = self.plc_client.is_connected()
        if current_connected != self._last_connection_state:
            with self._lock:
                # Update state inside lock
                self._last_connection_state = current_connected
            
            # Queue event to emit (outside lock)
            if current_connected:
                events_to_emit.append((EventType.CONNECTION_RESTORED, {
                    'message': 'PLC connection restored'
                }, Severity.INFO, None))
            else:
                events_to_emit.append((EventType.CONNECTION_LOST, {
                    'message': 'PLC connection lost'
                }, Severity.ERROR, None))
        
        # Emit events outside the lock to avoid blocking
        for event_type, data, severity, tag_name in events_to_emit:
            logger.debug(f"Emitting {event_type.value} event for {tag_name} with data: {data}")
            self._emit_event(event_type, data, severity, tag_name)
    
    def _evaluate_threshold(self, tag_name: str, value: Any, timestamp: datetime) -> None:
        """Evaluate tag value against failure conditions.
        
        Args:
            tag_name: Name of the tag
            value: Current tag value
            timestamp: Timestamp of the read
        """
        if tag_name not in self.config.tags:
            return
        
        tag_config = self.config.tags[tag_name]
        violation = False
        violation_reason = ""
        
        # Evaluate based on failure condition
        if tag_config.failure_condition == 'equals':
            if value == tag_config.failure_value:
                violation = True
                violation_reason = f"Value equals failure value: {tag_config.failure_value}"
        
        elif tag_config.failure_condition == 'not_equals':
            if value != tag_config.nominal:
                violation = True
                violation_reason = f"Value {value} does not equal nominal {tag_config.nominal}"
        
        elif tag_config.failure_condition == 'outside_range':
            if (tag_config.failure_threshold_low is not None and 
                value < tag_config.failure_threshold_low):
                violation = True
                violation_reason = f"Value {value} below threshold {tag_config.failure_threshold_low}"
            elif (tag_config.failure_threshold_high is not None and 
                  value > tag_config.failure_threshold_high):
                violation = True
                violation_reason = f"Value {value} above threshold {tag_config.failure_threshold_high}"
        
        elif tag_config.failure_condition == 'below':
            if tag_config.failure_threshold_low is not None and value < tag_config.failure_threshold_low:
                violation = True
                violation_reason = f"Value {value} below threshold {tag_config.failure_threshold_low}"
        
        elif tag_config.failure_condition == 'above':
            if tag_config.failure_threshold_high is not None and value > tag_config.failure_threshold_high:
                violation = True
                violation_reason = f"Value {value} above threshold {tag_config.failure_threshold_high}"
        
        # Handle violation (acquire lock only when modifying shared state)
        if violation:
            # Check if this is a new violation or existing one
            is_new_violation = False
            with self._lock:
                if tag_name not in self._active_violations:
                    # New violation
                    is_new_violation = True
                    self._total_violations += 1
                    violation_obj = ThresholdViolation(
                        tag_name=tag_name,
                        expected_value=tag_config.nominal,
                        actual_value=value,
                        failure_condition=tag_config.failure_condition,
                        timestamp=timestamp
                    )
                    self._active_violations[tag_name] = violation_obj
            
            # Emit violation event (outside lock)
            self._emit_event(EventType.THRESHOLD_VIOLATION, {
                'tag_name': tag_name,
                'expected_value': tag_config.nominal,
                'actual_value': value,
                'failure_condition': tag_config.failure_condition,
                'reason': violation_reason
            }, Severity.WARNING, tag_name)
            
            logger.warning(f"Threshold violation detected for {tag_name}: {violation_reason}")
            
            # Debug logging for auto-remediation conditions
            logger.debug(f"Auto-remediation check for {tag_name}:")
            logger.debug(f"  - is_new_violation: {is_new_violation}")
            logger.debug(f"  - auto_remediate config: {self.config.remediation.auto_remediate}")
            logger.debug(f"  - remediation_hook set: {self._remediation_hook is not None}")
            
            # Trigger auto-remediation if enabled and this is a new violation
            if is_new_violation and self.config.remediation.auto_remediate and self._remediation_hook:
                try:
                    # Default to 'reset' action for auto-remediation
                    # Could be made configurable per tag in the future
                    logger.info(f"Auto-remediation enabled: triggering reset for violation on {tag_name}")
                    self._remediation_hook('reset')
                    logger.info(f"Auto-remediation hook called successfully for {tag_name}")
                except Exception as e:
                    logger.error(f"Error triggering auto-remediation: {e}", exc_info=True)
            elif is_new_violation:
                # Log why auto-remediation didn't trigger (only for new violations)
                reasons = []
                if not self.config.remediation.auto_remediate:
                    reasons.append("auto_remediate is False")
                if not self._remediation_hook:
                    reasons.append("remediation hook not set")
                if reasons:
                    logger.debug(f"Auto-remediation not triggered for {tag_name}: {', '.join(reasons)}")
                else:
                    logger.debug(f"Auto-remediation not triggered for {tag_name}: unknown reason")
        else:
            # No violation - check if we need to resolve an existing one
            should_emit = False
            with self._lock:
                if tag_name in self._active_violations:
                    violation_obj = self._active_violations[tag_name]
                    violation_obj.resolved = True
                    violation_obj.resolved_at = timestamp
                    should_emit = True
            
            # Emit resolution event (outside lock)
            if should_emit:
                self._emit_event(EventType.THRESHOLD_VIOLATION, {
                    'tag_name': tag_name,
                    'resolved': True,
                    'message': f'Threshold violation resolved for {tag_name}'
                }, Severity.INFO, tag_name)
                
                # Remove from active violations after a delay (keep for history)
                # For now, we'll keep it but mark as resolved
                logger.info(f"Threshold violation resolved for {tag_name}")
    
    def _emit_event(self, event_type: EventType, data: Dict[str, Any], 
                   severity: Severity, tag_name: Optional[str] = None) -> None:
        """Emit an event via Socket.IO and store it.
        
        Args:
            event_type: Type of event
            data: Event data payload
            severity: Event severity
            tag_name: Optional tag name associated with event
        """
        event = Event(
            event_type=event_type,
            timestamp=datetime.now(),
            data=data,
            severity=severity,
            tag_name=tag_name
        )
        
        # Store event
        with self._lock:
            self._events.append(event)
        
        # Emit via Socket.IO if available
        if self.socketio:
            try:
                # Frontend expects the data payload directly for tag_read events
                # For connection events, frontend just needs the data dict (it calls addEvent which handles it)
                # For other events, emit the full event structure
                if event_type == EventType.TAG_READ:
                    emit_data = data
                elif event_type in (EventType.CONNECTION_RESTORED, EventType.CONNECTION_LOST):
                    # Connection events: frontend expects just the data dict
                    emit_data = data
                else:
                    # For other events, emit the full event structure
                    emit_data = event.to_dict()
                
                logger.debug(f"Emitting Socket.IO event: {event_type.value} with data: {emit_data}")
                self.socketio.emit(event_type.value, emit_data)
            except Exception as e:
                logger.warning(f"Error emitting Socket.IO event: {e}")
    
    def get_current_values(self) -> Dict[str, TagResult]:
        """Get current tag values.
        
        Returns:
            Dictionary of tag names to TagResult
        """
        with self._lock:
            # Make a shallow copy (TagResult objects are immutable)
            return dict(self._current_values)
    
    def get_tag_history(self, tag_name: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get historical values for a tag.
        
        Args:
            tag_name: Name of the tag
            limit: Maximum number of data points to return
            
        Returns:
            List of historical data points
        """
        with self._lock:
            if tag_name not in self._tag_history:
                return []
            
            history = list(self._tag_history[tag_name])
            if limit:
                history = history[-limit:]
            return history
    
    def get_events(self, event_type: Optional[EventType] = None, limit: int = 100) -> List[Event]:
        """Get recent events.
        
        Args:
            event_type: Optional filter by event type
            limit: Maximum number of events to return
            
        Returns:
            List of events
        """
        with self._lock:
            events = list(self._events)
            if event_type:
                events = [e for e in events if e.event_type == event_type]
            return events[-limit:]
    
    def get_active_violations(self) -> List[ThresholdViolation]:
        """Get active threshold violations.
        
        Returns:
            List of active violations
        """
        with self._lock:
            return [v for v in self._active_violations.values() if not v.resolved]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get monitoring statistics.
        
        Returns:
            Dictionary with statistics
        """
        with self._lock:
            uptime = (datetime.now() - self._start_time).total_seconds()
            connection_stats = self.plc_client.get_connection_stats()
            
            # Calculate connection uptime percent
            if connection_stats.connection_start_time:
                connection_uptime = (
                    datetime.now() - connection_stats.connection_start_time
                ).total_seconds()
                connection_uptime_percent = min(100.0, (connection_uptime / uptime) * 100) if uptime > 0 else 0.0
            else:
                connection_uptime_percent = 0.0
            
            return {
                'uptime_seconds': uptime,
                'total_tag_reads': self._total_reads,
                'total_violations': self._total_violations,
                'active_violations': len(self.get_active_violations()),
                'connection_uptime_percent': connection_uptime_percent,
                'connection_stats': connection_stats.to_dict()
            }
