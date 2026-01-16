"""REST API routes for PLC Self-Healing Middleware."""
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from flask import Blueprint, jsonify, request
from flask_socketio import SocketIO

from app.models import EventType, RemediationStatus
from app.config import AppConfig

logger = logging.getLogger(__name__)

# Global references (will be set by app initialization)
_monitor = None
_aap_client = None
_chaos_engine = None
_config = None
_socketio = None

# Remediation job tracking
_remediation_jobs: Dict[str, Dict[str, Any]] = {}
_last_remediation_time: Dict[str, datetime] = {}  # Per-tag remediation cooldown tracking
_last_remediation_time_global: Optional[datetime] = None  # Global cooldown for general remediation (no tag)
_last_job_status_check: Dict[str, datetime] = {}  # Track last time each job was checked (rate limiting)
JOB_STATUS_CHECK_INTERVAL_SECONDS = 2  # Minimum time between checking the same job (reduced from 3 to allow more frequent checks)


def init_api(monitor, aap_client, chaos_engine, config: AppConfig, socketio: SocketIO):
    """Initialize API with dependencies.
    
    Args:
        monitor: MonitorService instance
        aap_client: AAPClient instance
        chaos_engine: ChaosEngine instance
        config: AppConfig instance
        socketio: SocketIO instance
    """
    global _monitor, _aap_client, _chaos_engine, _config, _socketio
    _monitor = monitor
    _aap_client = aap_client
    _chaos_engine = chaos_engine
    _config = config
    _socketio = socketio


api = Blueprint('api', __name__, url_prefix='/api/v1')


def _api_response(success: bool, data: Any = None, error: str = None, status_code: int = 200) -> tuple:
    """Create standardized API response.
    
    Args:
        success: Whether the request was successful
        data: Response data
        error: Error message if any
        status_code: HTTP status code
        
    Returns:
        Tuple of (response dict, status code)
    """
    response = {
        'success': success,
        'timestamp': datetime.now().isoformat(),
        'data': data,
        'error': error
    }
    return jsonify(response), status_code


# Health & Status Endpoints

@api.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return _api_response(True, {'status': 'healthy'})


@api.route('/status', methods=['GET'])
def status():
    """Get current PLC connection status and tag values."""
    if not _monitor:
        logger.warning("Monitor service not initialized for /status request")
        return _api_response(False, None, 'Monitor service not initialized', 503)
    
    try:
        connection_stats = _monitor.plc_client.get_connection_stats()
        current_values = _monitor.get_current_values()
        
        # Build tag values dict
        tag_values_dict = {}
        for tag_name, result in current_values.items():
            try:
                tag_values_dict[tag_name] = result.to_dict()
            except Exception as e:
                logger.warning(f"Error converting tag {tag_name} to dict: {e}")
                tag_values_dict[tag_name] = {
                    'tag_name': tag_name,
                    'success': False,
                    'error': f'Error serializing: {str(e)}'
                }
        
        response_data = {
            'connected': connection_stats.connected,
            'connection_stats': connection_stats.to_dict(),
            'tag_values': tag_values_dict
        }
        
        return _api_response(True, response_data)
    except Exception as e:
        logger.error(f"Error in /status endpoint: {e}", exc_info=True)
        return _api_response(False, None, f'Error getting status: {str(e)}', 500)


# Tags & Metrics Endpoints

@api.route('/tags', methods=['GET'])
def get_tags():
    """Get current values for all configured tags."""
    if not _monitor:
        return _api_response(False, None, 'Monitor service not initialized', 503)
    
    current_values = _monitor.get_current_values()
    
    return _api_response(True, {
        tag_name: result.to_dict()
        for tag_name, result in current_values.items()
    })


@api.route('/tags/<tag_name>', methods=['GET'])
def get_tag(tag_name: str):
    """Get specific tag value and history."""
    if not _monitor:
        return _api_response(False, None, 'Monitor service not initialized', 503)
    
    # Get limit from query params
    limit = request.args.get('limit', type=int, default=100)
    
    current_values = _monitor.get_current_values()
    history = _monitor.get_tag_history(tag_name, limit=limit)
    
    if tag_name not in current_values:
        return _api_response(False, None, f'Tag {tag_name} not found', 404)
    
    return _api_response(True, {
        'current': current_values[tag_name].to_dict(),
        'history': history
    })


@api.route('/metrics', methods=['GET'])
def get_metrics():
    """Get aggregated metrics."""
    if not _monitor:
        return _api_response(False, None, 'Monitor service not initialized', 503)
    
    stats = _monitor.get_statistics()
    current_values = _monitor.get_current_values()
    
    return _api_response(True, {
        **stats,
        'tag_values': {
            tag_name: result.value if result.success else None
            for tag_name, result in current_values.items()
        }
    })


@api.route('/metrics/history', methods=['GET'])
def get_metrics_history():
    """Get historical metrics (placeholder - in-memory only for now)."""
    # In future, this would query a database
    return _api_response(True, {
        'message': 'Historical metrics not yet implemented (in-memory storage only)',
        'data': []
    })


# Events & Logs Endpoints

@api.route('/events', methods=['GET'])
def get_events():
    """Get recent events."""
    if not _monitor:
        return _api_response(False, None, 'Monitor service not initialized', 503)
    
    # Query parameters
    event_type = request.args.get('type')
    limit = request.args.get('limit', type=int, default=100)
    
    # Filter by type if specified
    filter_type = None
    if event_type:
        try:
            filter_type = EventType(event_type)
        except ValueError:
            return _api_response(False, None, f'Invalid event type: {event_type}', 400)
    
    events = _monitor.get_events(event_type=filter_type, limit=limit)
    
    return _api_response(True, {
        'events': [event.to_dict() for event in events],
        'count': len(events)
    })


@api.route('/events/violations', methods=['GET'])
def get_violations():
    """Get active threshold violations."""
    logger.debug("API /events/violations endpoint called")
    if not _monitor:
        logger.warning("Monitor service not initialized for /events/violations request")
        return _api_response(False, None, 'Monitor service not initialized', 503)
    
    try:
        active_only = request.args.get('active', 'true').lower() == 'true'
        
        violations = _monitor.get_active_violations()
        logger.debug(f"/events/violations returning: count={len(violations)}, active_only={active_only}")
        
        if not active_only:
            # Include resolved violations (would need to track these separately)
            pass
        
        return _api_response(True, {
            'violations': [v.to_dict() for v in violations],
            'count': len(violations)
        })
    except Exception as e:
        logger.error(f"Error in /events/violations endpoint: {e}", exc_info=True)
        return _api_response(False, None, f'Error getting violations: {str(e)}', 500)


@api.route('/logs', methods=['GET'])
def get_logs():
    """Get application logs (placeholder)."""
    # In a real implementation, this would read from log files
    return _api_response(True, {
        'message': 'Log retrieval not yet implemented',
        'logs': []
    })


# Remediation Endpoints

@api.route('/remediate/stop', methods=['POST'])
def remediate_stop():
    """Trigger emergency stop remediation."""
    data = request.get_json() or {}
    tag_name = data.get('tag_name')
    return _trigger_remediation('stop', tag_name=tag_name)


@api.route('/remediate/reset', methods=['POST'])
def remediate_reset():
    """Trigger emergency reset remediation."""
    data = request.get_json() or {}
    tag_name = data.get('tag_name')
    return _trigger_remediation('reset', tag_name=tag_name)


@api.route('/remediate/restart', methods=['POST'])
def remediate_restart():
    """Trigger emergency restart remediation."""
    data = request.get_json() or {}
    tag_name = data.get('tag_name')
    return _trigger_remediation('restart', tag_name=tag_name)


def _is_tag_in_remediation_cooldown(tag_name: Optional[str]) -> tuple:
    """Check if a tag (or global) is in remediation cooldown.
    
    Args:
        tag_name: Tag name to check, or None for global cooldown
        
    Returns:
        Tuple of (is_in_cooldown, remaining_seconds)
    """
    global _last_remediation_time, _last_remediation_time_global
    
    if not _config:
        return (False, 0.0)
    
    cooldown = _config.remediation.cooldown_seconds
    now = datetime.now()
    
    if tag_name:
        # Check per-tag cooldown
        if tag_name in _last_remediation_time:
            elapsed = (now - _last_remediation_time[tag_name]).total_seconds()
            if elapsed < cooldown:
                remaining = cooldown - elapsed
                return (True, remaining)
    else:
        # Check global cooldown for general remediation
        if _last_remediation_time_global:
            elapsed = (now - _last_remediation_time_global).total_seconds()
            if elapsed < cooldown:
                remaining = cooldown - elapsed
                return (True, remaining)
    
    return (False, 0.0)


def _trigger_remediation(action: str, tag_name: Optional[str] = None) -> tuple:
    """Internal function to trigger remediation.
    
    Args:
        action: Action type (stop, reset, restart)
        tag_name: Optional tag name that triggered the remediation
        
    Returns:
        API response tuple
    """
    global _last_remediation_time, _last_remediation_time_global
    
    if not _aap_client:
        return _api_response(False, None, 'AAP client not initialized', 503)
    
    if not _config:
        return _api_response(False, None, 'Configuration not loaded', 503)
    
    # Check cooldown (per-tag or global)
    is_in_cooldown, remaining = _is_tag_in_remediation_cooldown(tag_name)
    if is_in_cooldown:
        cooldown_type = f"tag '{tag_name}'" if tag_name else "global"
        return _api_response(
            False, None,
            f'Remediation cooldown active for {cooldown_type}. Wait {remaining:.1f} more seconds.',
            429
        )
    
    # Get job template ID
    template_key = f'emergency_{action}'
    if template_key not in _config.aap.job_templates:
        return _api_response(False, None, f'Job template not configured for {action}', 404)
    
    template_id = _config.aap.job_templates[template_key]
    
    # Launch job
    try:
        job_result = _aap_client.launch_job(template_id)
        
        if not job_result.get('success'):
            return _api_response(False, None, f'Failed to launch remediation job: {job_result.get("error")}', 500)
        
        # Create remediation job record
        job_id = str(uuid.uuid4())
        aap_job_id = job_result.get('job_id')
        
        remediation_job = {
            'job_id': job_id,
            'action_type': action,
            'status': RemediationStatus.PENDING.value,
            'start_time': datetime.now().isoformat(),
            'aap_job_id': aap_job_id,
            'tag_name': tag_name  # Track which tag triggered this remediation (if any)
        }
        
        _remediation_jobs[job_id] = remediation_job
        
        # Update cooldown (per-tag or global)
        now = datetime.now()
        if tag_name:
            _last_remediation_time[tag_name] = now
            logger.debug(f"Updated per-tag cooldown for '{tag_name}'")
        else:
            _last_remediation_time_global = now
            logger.debug("Updated global remediation cooldown")
        
        # Emit event
        if _socketio:
            _socketio.emit('remediation_triggered', {
                'job_id': job_id,
                'action': action,
                'aap_job_id': aap_job_id
            })
        
        logger.info(f"Remediation triggered: {action} (job_id={job_id}, aap_job_id={aap_job_id})")
        
        return _api_response(True, {
            'job_id': job_id,
            'action': action,
            'aap_job_id': aap_job_id,
            'status': 'pending'
        })
        
    except Exception as e:
        logger.error(f"Error triggering remediation: {e}", exc_info=True)
        return _api_response(False, None, f'Error triggering remediation: {str(e)}', 500)


@api.route('/remediate/status', methods=['GET'])
def get_remediation_status():
    """Get current remediation job status."""
    job_id = request.args.get('job_id')
    
    if job_id:
        # Get specific job
        if job_id not in _remediation_jobs:
            return _api_response(False, None, f'Job {job_id} not found', 404)
        
        job = _remediation_jobs[job_id]
        old_status = job.get('status')
        
        # Update status from AAP if available (only check if not already finished)
        current_status = job.get('status')
        if (job.get('aap_job_id') and _aap_client and 
            current_status not in ['successful', 'failed']):
            # Check rate limiting - don't check same job too frequently
            job_key = job.get('job_id', '')
            now = datetime.now()
            should_check = True
            
            if job_key in _last_job_status_check:
                elapsed = (now - _last_job_status_check[job_key]).total_seconds()
                if elapsed < JOB_STATUS_CHECK_INTERVAL_SECONDS:
                    should_check = False
                    logger.debug(f"Skipping status check for job {job_key} (checked {elapsed:.1f}s ago, need {JOB_STATUS_CHECK_INTERVAL_SECONDS}s)")
            
            if should_check:
                try:
                    _last_job_status_check[job_key] = now
                    aap_status = _aap_client.get_job_status(job['aap_job_id'])
                    if aap_status.get('finished'):
                        new_status = 'successful' if not aap_status.get('failed') else 'failed'
                        job['status'] = new_status
                        job['end_time'] = datetime.now().isoformat()
                        
                        # Clear violation if job just became successful and has a tag_name
                        if new_status == 'successful' and old_status != 'successful' and job.get('tag_name') and _monitor:
                            try:
                                tag_name = job['tag_name']
                                logger.info(f"Attempting to clear violation for tag_name='{tag_name}' after successful remediation job {job_id}")
                                _monitor.clear_violation(tag_name)
                                logger.info(f"Cleared violation for '{tag_name}' after successful remediation job {job_id}")
                            except Exception as e:
                                logger.warning(f"Error clearing violation for {job['tag_name']}: {e}", exc_info=True)
                except Exception as e:
                    logger.warning(f"Error checking AAP job status: {e}")
        
        return _api_response(True, job)
    else:
        # Get all jobs - check AAP status for each job (optimized)
        jobs_list = []
        now = datetime.now()
        
        # Clean up old cooldown entries (older than 1 hour)
        tags_to_remove = [
            tag for tag, last_time in _last_remediation_time.items()
            if (now - last_time).total_seconds() > 3600
        ]
        for tag in tags_to_remove:
            del _last_remediation_time[tag]
            logger.debug(f"Cleaned up old cooldown entry for tag '{tag}'")
        
        # Clean up old job status check entries (older than 1 hour)
        job_checks_to_remove = [
            job_id for job_id, last_check in _last_job_status_check.items()
            if (now - last_check).total_seconds() > 3600
        ]
        for job_id in job_checks_to_remove:
            del _last_job_status_check[job_id]
        
        # Limit how many jobs we check per request to prevent overload
        MAX_JOBS_TO_CHECK = 10
        jobs_to_check = []
        jobs_skipped_finished = 0
        jobs_skipped_rate_limited = []
        active_jobs = []
        
        # First pass: collect active jobs and categorize them
        for job in _remediation_jobs.values():
            current_status = job.get('status')
            job_id = job.get('job_id', '')
            
            # Skip finished jobs entirely
            if current_status in ['successful', 'failed']:
                jobs_skipped_finished += 1
                continue
            
            # Collect active jobs that can be checked
            if job.get('aap_job_id') and _aap_client:
                active_jobs.append(job)
        
        # Second pass: select jobs to check, ensuring at least one if there are active jobs
        for job in active_jobs:
            if len(jobs_to_check) >= MAX_JOBS_TO_CHECK:
                break
            
            job_id = job.get('job_id', '')
            
            # Check rate limiting
            should_check = True
            if job_id in _last_job_status_check:
                elapsed = (now - _last_job_status_check[job_id]).total_seconds()
                if elapsed < JOB_STATUS_CHECK_INTERVAL_SECONDS:
                    should_check = False
                    jobs_skipped_rate_limited.append(job_id)
            
            if should_check:
                jobs_to_check.append(job)
        
        # If no jobs were selected but there are active jobs, check the oldest unchecked job
        # This ensures jobs don't get stuck
        if len(jobs_to_check) == 0 and len(active_jobs) > 0:
            # Find the job that was checked longest ago (or never checked)
            oldest_job = None
            oldest_check_time = None
            
            for job in active_jobs:
                job_id = job.get('job_id', '')
                if job_id not in _last_job_status_check:
                    # Never checked - prioritize this one
                    oldest_job = job
                    break
                else:
                    check_time = _last_job_status_check[job_id]
                    if oldest_check_time is None or check_time < oldest_check_time:
                        oldest_check_time = check_time
                        oldest_job = job
            
            if oldest_job:
                jobs_to_check.append(oldest_job)
                if oldest_job.get('job_id', '') in jobs_skipped_rate_limited:
                    jobs_skipped_rate_limited.remove(oldest_job.get('job_id', ''))
        
        # Check status for selected jobs
        for job in jobs_to_check:
            old_status = job.get('status')
            job_id = job.get('job_id', '')
            
            try:
                _last_job_status_check[job_id] = now
                aap_status = _aap_client.get_job_status(job['aap_job_id'])
                if aap_status.get('finished'):
                    new_status = 'successful' if not aap_status.get('failed') else 'failed'
                    job['status'] = new_status
                    job['end_time'] = datetime.now().isoformat()
                    
                    # Clear violation if job just became successful and has a tag_name
                    if new_status == 'successful' and old_status != 'successful' and job.get('tag_name') and _monitor:
                        try:
                            tag_name = job['tag_name']
                            logger.info(f"Attempting to clear violation for tag_name='{tag_name}' after successful remediation job {job_id}")
                            _monitor.clear_violation(tag_name)
                            logger.info(f"Cleared violation for '{tag_name}' after successful remediation job {job_id}")
                        except Exception as e:
                            logger.warning(f"Error clearing violation for {job.get('tag_name')}: {e}", exc_info=True)
            except Exception as e:
                logger.warning(f"Error checking AAP job status for job {job_id}: {e}")
        
        # Add all jobs to response (including ones we didn't check)
        for job in _remediation_jobs.values():
            jobs_list.append(job)
        
        total_active_jobs = len(active_jobs)
        if len(jobs_to_check) > 0 or jobs_skipped_finished > 0 or len(jobs_skipped_rate_limited) > 0:
            logger.debug(f"Status check: checked {len(jobs_to_check)}/{total_active_jobs} active jobs, "
                        f"skipped {jobs_skipped_finished} finished, {len(jobs_skipped_rate_limited)} rate-limited")
        
        return _api_response(True, {
            'jobs': jobs_list,
            'count': len(jobs_list)
        })


# Chaos Engineering Endpoints

@api.route('/chaos/status', methods=['GET'])
def get_chaos_status():
    """Get chaos engine status."""
    if not _chaos_engine:
        return _api_response(False, None, 'Chaos engine not initialized', 503)
    
    return _api_response(True, _chaos_engine.get_status())


@api.route('/chaos/enable', methods=['POST'])
def enable_chaos():
    """Enable chaos injection."""
    if not _chaos_engine:
        return _api_response(False, None, 'Chaos engine not initialized', 503)
    
    _chaos_engine.enable()
    return _api_response(True, {'message': 'Chaos injection enabled'})


@api.route('/chaos/disable', methods=['POST'])
def disable_chaos():
    """Disable chaos injection."""
    if not _chaos_engine:
        return _api_response(False, None, 'Chaos engine not initialized', 503)
    
    _chaos_engine.disable()
    return _api_response(True, {'message': 'Chaos injection disabled'})


@api.route('/chaos/inject', methods=['POST'])
def inject_chaos():
    """Manually inject a specific failure."""
    if not _chaos_engine:
        return _api_response(False, None, 'Chaos engine not initialized', 503)
    
    data = request.get_json() or {}
    failure_type = data.get('failure_type')
    
    if not failure_type:
        return _api_response(False, None, 'Missing required parameter: failure_type', 400)
    
    try:
        result = _chaos_engine.inject_failure(failure_type, **data)
        
        if result.get('success'):
            # Emit event
            if _socketio:
                _socketio.emit('chaos_injection', {
                    'failure_type': failure_type,
                    'timestamp': datetime.now().isoformat()
                })
        
        return _api_response(result.get('success', False), result, result.get('error'))
    except Exception as e:
        logger.error(f"Error injecting chaos: {e}", exc_info=True)
        return _api_response(False, None, f'Error injecting failure: {str(e)}', 500)


# Configuration Endpoint

@api.route('/config', methods=['GET'])
def get_config():
    """Get current configuration (sanitized, no secrets)."""
    if not _config:
        return _api_response(False, None, 'Configuration not loaded', 503)
    
    # Return sanitized config (no tokens/secrets)
    config_dict = {
        'plc': {
            'ip_address': _config.plc.ip_address,
            'slot': _config.plc.slot,
            'timeout': _config.plc.timeout,
            'poll_interval_ms': _config.plc.poll_interval_ms
        },
        'tags': {
            tag_name: {
                'name': tag.name,
                'type': tag.type,
                'nominal': tag.nominal,
                'failure_condition': tag.failure_condition,
                'failure_value': tag.failure_value,
                'failure_threshold_low': tag.failure_threshold_low,
                'failure_threshold_high': tag.failure_threshold_high
            }
            for tag_name, tag in _config.tags.items()
        },
        'aap': {
            'enabled': _config.aap.enabled,
            'mock_mode': _config.aap.mock_mode,
            'base_url': _config.aap.base_url if _config.aap.base_url else '[not set]',
            'verify_ssl': _config.aap.verify_ssl,
            'job_templates': _config.aap.job_templates
        },
        'remediation': {
            'auto_remediate': _config.remediation.auto_remediate,
            'cooldown_seconds': _config.remediation.cooldown_seconds,
            'max_retries': _config.remediation.max_retries
        },
        'chaos': {
            'enabled': _config.chaos.enabled,
            'failure_injection_rate': _config.chaos.failure_injection_rate,
            'failure_types': _config.chaos.failure_types
        },
        'dashboard': {
            'refresh_interval_ms': _config.dashboard.refresh_interval_ms,
            'history_retention_hours': _config.dashboard.history_retention_hours,
            'chart_data_points': _config.dashboard.chart_data_points
        },
        'logging': {
            'level': _config.logging.level,
            'format': _config.logging.format
        }
    }
    
    return _api_response(True, config_dict)
