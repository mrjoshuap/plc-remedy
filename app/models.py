"""Data models for PLC Self-Healing Middleware."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, List


class EventType(Enum):
    """Event type enumeration."""
    TAG_READ = "tag_read"
    THRESHOLD_VIOLATION = "threshold_violation"
    REMEDIATION_TRIGGERED = "remediation_triggered"
    REMEDIATION_COMPLETED = "remediation_completed"
    REMEDIATION_FAILED = "remediation_failed"
    CONNECTION_LOST = "connection_lost"
    CONNECTION_RESTORED = "connection_restored"
    CHAOS_INJECTION = "chaos_injection"


class Severity(Enum):
    """Event severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class RemediationStatus(Enum):
    """Remediation job status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESSFUL = "successful"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TagResult:
    """Result of a PLC tag read operation."""
    tag_name: str
    value: Any
    timestamp: datetime
    success: bool
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'tag_name': self.tag_name,
            'value': self.value,
            'timestamp': self.timestamp.isoformat(),
            'success': self.success,
            'error': self.error
        }


@dataclass
class ConnectionStats:
    """PLC connection statistics."""
    connected: bool
    last_successful_read: Optional[datetime] = None
    total_reads: int = 0
    total_errors: int = 0
    connection_start_time: Optional[datetime] = None
    last_error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'connected': self.connected,
            'last_successful_read': (
                self.last_successful_read.isoformat() 
                if self.last_successful_read else None
            ),
            'total_reads': self.total_reads,
            'total_errors': self.total_errors,
            'connection_start_time': (
                self.connection_start_time.isoformat()
                if self.connection_start_time else None
            ),
            'last_error': self.last_error
        }


@dataclass
class Event:
    """Application event."""
    event_type: EventType
    timestamp: datetime
    data: Dict[str, Any]
    severity: Severity = Severity.INFO
    tag_name: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'event_type': self.event_type.value,
            'timestamp': self.timestamp.isoformat(),
            'data': self.data,
            'severity': self.severity.value,
            'tag_name': self.tag_name
        }


@dataclass
class RemediationJob:
    """Remediation job tracking."""
    job_id: str
    action_type: str  # stop, reset, restart
    status: RemediationStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    error_message: Optional[str] = None
    aap_job_id: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'job_id': self.job_id,
            'action_type': self.action_type,
            'status': self.status.value,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'error_message': self.error_message,
            'aap_job_id': self.aap_job_id
        }


@dataclass
class MetricSnapshot:
    """Aggregated metrics at a point in time."""
    timestamp: datetime
    uptime_seconds: float
    total_tag_reads: int
    total_violations: int
    active_violations: int
    total_remediations: int
    connection_uptime_percent: float
    tag_values: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'uptime_seconds': self.uptime_seconds,
            'total_tag_reads': self.total_tag_reads,
            'total_violations': self.total_violations,
            'active_violations': self.active_violations,
            'total_remediations': self.total_remediations,
            'connection_uptime_percent': self.connection_uptime_percent,
            'tag_values': self.tag_values
        }


@dataclass
class ThresholdViolation:
    """Threshold violation information."""
    tag_name: str
    expected_value: Any
    actual_value: Any
    failure_condition: str
    timestamp: datetime
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'tag_name': self.tag_name,
            'expected_value': self.expected_value,
            'actual_value': self.actual_value,
            'failure_condition': self.failure_condition,
            'timestamp': self.timestamp.isoformat(),
            'resolved': self.resolved,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None
        }
