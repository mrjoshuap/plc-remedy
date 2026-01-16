"""Application entry point for PLC Self-Healing Middleware."""
# Monkey patch for eventlet BEFORE any other imports
import eventlet
eventlet.monkey_patch()

import logging
import os
import sys
import atexit
import signal
from flask import Flask
from flask_socketio import SocketIO

from app.config import load_config, get_config
from app.plc_client import PLCClient
from app.aap_client import AAPClient
from app.monitor import MonitorService
from app.chaos import ChaosEngine
from app.api import api, init_api
from app.web import web

# Configure basic logging first (will be reconfigured after config loads)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Global instances (will be initialized in create_app)
config = None
plc_client = None
aap_client = None
monitor_service = None
chaos_engine = None
socketio = None

_shutdown_registered = False

def register_shutdown_handlers():
    """Register shutdown handlers for graceful cleanup."""
    global _shutdown_registered
    if _shutdown_registered:
        return
    _shutdown_registered = True
    
    def cleanup():
        """Cleanup function - runs in a separate thread to avoid blocking."""
        global monitor_service, plc_client
        logger.info("Shutting down application...")
        
        # Stop monitor service (has timeout, won't block forever)
        if monitor_service:
            try:
                monitor_service.stop()
            except Exception as e:
                logger.warning(f"Error stopping monitor service: {e}")
        
        # Disconnect PLC (brief operation, but use try/except)
        if plc_client:
            try:
                plc_client.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting PLC: {e}")
        
        logger.info("Application shutdown complete")
    
    # Register cleanup on exit
    atexit.register(cleanup)
    
    # Register signal handlers
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating shutdown...")
        # Run cleanup in a thread to avoid blocking signal handler
        import threading
        cleanup_thread = threading.Thread(target=cleanup, daemon=True)
        cleanup_thread.start()
        cleanup_thread.join(timeout=2.0)  # Wait max 2 seconds for cleanup
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def create_app():
    """Create and configure the Flask application.
    
    Returns:
        Configured Flask app
    """
    global config, plc_client, aap_client, monitor_service, chaos_engine, socketio
    
    # Initialize Flask app
    # Set template folder to app/templates
    template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app', 'templates')
    app = Flask(__name__, template_folder=template_dir)
    app.config['SECRET_KEY'] = 'plc-remedy-secret-key-change-in-production'
    
    # Initialize Socket.IO (assign to global)
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')
    
    try:
        # Load configuration
        logger.info("Loading configuration...")
        config = load_config()
        logger.info(f"Configuration loaded: PLC at {config.plc.ip_address}")
        
        # Configure logging based on config
        log_level = getattr(logging, config.logging.level.upper(), logging.INFO)
        logging.basicConfig(
            level=log_level,
            format=config.logging.format,
            handlers=[
                logging.StreamHandler(sys.stdout)
            ],
            force=True  # Override previous configuration
        )
        logger.info(f"Logging configured: level={config.logging.level}")
        
        # Initialize PLC client
        logger.info("Initializing PLC client...")
        # Pass tags config for mock mode tag population
        plc_client = PLCClient(config.plc, tags_config=config.tags if config.plc.mock_mode else None)
        
        # Initialize AAP client
        logger.info("Initializing AAP client...")
        aap_client = AAPClient(config.aap)
        
        # Initialize chaos engine
        logger.info("Initializing chaos engine...")
        chaos_engine = ChaosEngine(config.chaos, config)
        
        # Initialize monitor service
        logger.info("Initializing monitor service...")
        monitor_service = MonitorService(config, plc_client, socketio)
        
        # Set chaos injection hook
        chaos_hook = chaos_engine.get_injection_hook()
        if chaos_hook:
            monitor_service.set_chaos_hook(chaos_hook)
        
        # Set remediation hook for auto-remediation
        def remediation_hook(action: str) -> None:
            """Trigger remediation action (for auto-remediation hook)."""
            from datetime import datetime
            import uuid
            from app.models import RemediationStatus
            from app.api.routes import _remediation_jobs, _last_remediation_time as api_last_remediation_time
            
            logger.info(f"Remediation hook called with action: {action}")
            
            if not aap_client:
                logger.warning("AAP client not available for auto-remediation")
                return
            
            # Check cooldown (use API module's last remediation time)
            if api_last_remediation_time:
                cooldown = config.remediation.cooldown_seconds
                elapsed = (datetime.now() - api_last_remediation_time).total_seconds()
                if elapsed < cooldown:
                    remaining = cooldown - elapsed
                    logger.info(f"Auto-remediation skipped: cooldown active ({remaining:.1f}s remaining)")
                    return
            
            # Get job template ID
            template_key = f'emergency_{action}'
            if template_key not in config.aap.job_templates:
                logger.warning(f"Job template not configured for {action}")
                return
            
            template_id = config.aap.job_templates[template_key]
            
            # Launch job
            try:
                job_result = aap_client.launch_job(template_id)
                
                if not job_result.get('success'):
                    logger.error(f"Failed to launch auto-remediation job: {job_result.get('error')}")
                    return
                
                # Create remediation job record
                job_id = str(uuid.uuid4())
                aap_job_id = job_result.get('job_id')
                
                remediation_job = {
                    'job_id': job_id,
                    'action_type': action,
                    'status': RemediationStatus.PENDING.value,
                    'start_time': datetime.now().isoformat(),
                    'aap_job_id': aap_job_id
                }
                
                # Add to API routes' remediation jobs dictionary
                _remediation_jobs[job_id] = remediation_job
                
                # Update last remediation time in API module
                import app.api.routes as api_routes
                api_routes._last_remediation_time = datetime.now()
                
                # Emit event
                if socketio:
                    socketio.emit('remediation_triggered', {
                        'job_id': job_id,
                        'action': action,
                        'aap_job_id': aap_job_id
                    })
                
                logger.info(f"Auto-remediation triggered: {action} (job_id={job_id}, aap_job_id={aap_job_id})")
                
            except Exception as e:
                logger.error(f"Error triggering auto-remediation: {e}", exc_info=True)
        
        logger.info(f"Setting remediation hook on monitor service (auto_remediate={config.remediation.auto_remediate})")
        monitor_service.set_remediation_hook(remediation_hook)
        logger.info("Remediation hook set on monitor service")
        
        # Initialize API with dependencies
        init_api(monitor_service, aap_client, chaos_engine, config, socketio)
        
        # Register blueprints
        app.register_blueprint(api)
        app.register_blueprint(web)
        
        # Register shutdown handlers
        register_shutdown_handlers()
        
        return app
        
    except Exception as e:
        logger.error(f"Error initializing application: {e}", exc_info=True)
        raise


# Create app instance
app = create_app()


@app.route('/health')
def health():
    """Simple health check endpoint."""
    return {'status': 'healthy'}, 200

# Note: teardown_appcontext is called for EACH request, not just shutdown
# Actual shutdown is handled by register_shutdown_handlers() via signal handlers


if __name__ == '__main__':
    # Development mode - run with Flask's built-in server
    # Disable debug mode to prevent reloader from disconnecting PLC
    logger.info("Starting application in development mode...")
    if socketio is None:
        logger.error("SocketIO not initialized!")
        sys.exit(1)
    
    # Connect to PLC and start monitor in background using a regular thread
    # (not eventlet greenlet, to avoid blocking the event loop)
    import threading
    def initialize_background():
        """Initialize PLC connection and monitor service in background."""
        try:
            # Small delay to ensure server is fully started
            import time
            time.sleep(0.5)
            logger.info("Connecting to PLC...")
            if plc_client.connect():
                logger.info("Successfully connected to PLC")
            else:
                logger.warning("Failed to connect to PLC on startup. Will retry during monitoring.")
            
            # Start monitor service
            logger.info("Starting monitor service...")
            monitor_service.start()
            logger.info("Monitor service started")
        except Exception as e:
            logger.error(f"Error in background initialization: {e}", exc_info=True)
    
    # Start background thread (daemon so it doesn't prevent shutdown)
    init_thread = threading.Thread(target=initialize_background, daemon=True)
    init_thread.start()
    
    # Use debug=False to prevent reloader from restarting and disconnecting PLC
    # Set use_reloader=False explicitly to avoid connection issues
    socketio.run(app, host='0.0.0.0', port=15000, debug=False, use_reloader=False)
else:
    # Production mode - gunicorn will call create_app()
    logger.info("Application initialized for production (gunicorn)")
