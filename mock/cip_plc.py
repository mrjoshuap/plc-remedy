"""Full CIP protocol-compatible PLC simulator using cpppo."""
import argparse
import logging
import os
import threading
import time
from typing import Optional

try:
    from flask import Flask, request, jsonify
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

try:
    from cpppo.server.enip import device
    from cpppo.server.enip import get_attribute
    CPPPO_AVAILABLE = True
except ImportError:
    CPPPO_AVAILABLE = False
    logging.warning("cpppo not available. Please install dependencies from requirements.txt")

try:
    from mock.tag_manager import TagManager, OperatingMode
    from mock.cip_objects import TagObject, ConnectionManager, IdentityObject
    from mock.cip_services import CIPServiceHandler
except ImportError:
    # Handle relative imports
    from tag_manager import TagManager, OperatingMode
    from cip_objects import TagObject, ConnectionManager, IdentityObject
    from cip_services import CIPServiceHandler

_log_level = getattr(logging, os.environ.get('LOG_LEVEL', 'INFO').upper(), logging.INFO)
logging.basicConfig(
    level=_log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Global tag manager (set by CIPPLC instance before starting server)
_global_tag_manager = None


def set_global_tag_manager(tag_manager):
    """Set global tag manager for ModeAwareAttribute instances."""
    global _global_tag_manager
    _global_tag_manager = tag_manager


class ModeAwareAttribute(device.Attribute):
    """cpppo Attribute that applies operating mode transformations.

    cpppo calls this with (name, parser) signature, so we use global tag_manager.
    """

    def __init__(self, *args, **kwargs):
        """Initialize mode-aware attribute.

        cpppo calls this with keyword arguments: attr_cls(**attr_kwds)
        where attr_kwds contains 'name' and 'type_cls' (the parser/type class).

        Args:
            *args: Positional arguments (cpppo may pass parser as first arg)
            **kwargs: Keyword arguments containing 'name' and 'type_cls'
        """
        # Extract name from kwargs (cpppo passes it as keyword argument)
        name = kwargs.pop('name', None)

        # Extract parser/type_cls from kwargs (cpppo uses 'type_cls' not 'parser')
        parser = kwargs.pop('type_cls', None)
        if parser is None:
            # Try 'parser' as fallback
            parser = kwargs.pop('parser', None)
        if parser is None and len(args) > 0:
            # Parser might be first positional argument
            parser = args[0]
            args = args[1:]

        # Validate we have required arguments
        if name is None:
            raise TypeError("ModeAwareAttribute.__init__() missing required argument 'name'")
        if parser is None:
            raise TypeError("ModeAwareAttribute.__init__() missing required argument 'type_cls' (parser)")

        # Call parent class - it expects name as first positional arg and type_cls as keyword
        # Put type_cls back in kwargs for parent
        kwargs['type_cls'] = parser
        # Parent expects: __init__(name, type_cls=..., **kwargs)
        super().__init__(name, *args, **kwargs)
        self.tag_name = name
        # name is already set by parent, but we keep tag_name for our use

    def __getitem__(self, key):
        """Get tag value with mode transformation.

        Args:
            key: Index or slice. If slice, returns a list; if index, returns single value.
        """
        global _global_tag_manager

        if _global_tag_manager is None:
            logger.warning(f"Tag manager not set for {self.tag_name}")
            return 0 if not isinstance(key, slice) else [0]

        try:
            value = _global_tag_manager.get_tag_value(self.tag_name)
            if isinstance(key, slice):
                return [value]
            return value
        except KeyError:
            logger.warning(f"Tag {self.tag_name} not found in tag manager")
            return 0 if not isinstance(key, slice) else [0]
        except Exception as e:
            logger.error(f"Error reading tag {self.tag_name}: {e}", exc_info=True)
            return 0 if not isinstance(key, slice) else [0]

    def __setitem__(self, key, value):
        """Set tag value."""
        global _global_tag_manager

        if _global_tag_manager is None:
            logger.warning(f"Tag manager not set for {self.tag_name}")
            return

        try:
            _global_tag_manager.set_tag_value(self.tag_name, value)
        except Exception as e:
            logger.error(f"Failed to set tag {self.tag_name}: {e}", exc_info=True)


class CIPPLC:
    """Full CIP protocol-compatible PLC simulator."""

    def __init__(self, ip: str = "0.0.0.0", port: int = 44818,
                 mode: OperatingMode = OperatingMode.NORMAL,
                 control_port: int = 18080):
        """Initialize CIP PLC simulator.

        Args:
            ip: IP address to bind to
            port: Port to listen on (CIP default is 44818)
            mode: Operating mode
            control_port: Port for HTTP control API
        """
        if not CPPPO_AVAILABLE:
            raise ImportError("cpppo is required. Please install dependencies from requirements.txt or see documentation for setup instructions.")

        self.ip = ip
        self.port = port
        self.mode = mode
        self.control_port = control_port
        self.running = False

        # Initialize components
        self.tag_manager = TagManager(mode)
        self.tag_manager.set_mode(mode)

        self.tag_object = TagObject(self.tag_manager)
        self.connection_manager = ConnectionManager()
        self.identity_object = IdentityObject()
        self.service_handler = CIPServiceHandler(
            self.tag_object, self.connection_manager, self.identity_object
        )

        # cpppo server components
        self.server: Optional[device.Device] = None
        self.server_thread: Optional[threading.Thread] = None
        self.watchdog_thread: Optional[threading.Thread] = None
        self.stats_logger_thread: Optional[threading.Thread] = None
        self._control_server_thread: Optional[threading.Thread] = None

    def start(self):
        """Start the CIP PLC server."""
        if self.running:
            logger.warning("CIP PLC already running")
            return

        try:
            # Start server in background thread
            self.running = True
            self.server_thread = threading.Thread(
                target=self._run_server,
                daemon=True
            )
            self.server_thread.start()

            # Start watchdog thread to monitor server health
            self.watchdog_thread = threading.Thread(
                target=self._watchdog_thread,
                daemon=True
            )
            self.watchdog_thread.start()

            # Start statistics logger thread
            self.stats_logger_thread = threading.Thread(
                target=self._stats_logger_thread,
                daemon=True
            )
            self.stats_logger_thread.start()

            # Start HTTP control API thread
            if FLASK_AVAILABLE:
                self._control_server_thread = threading.Thread(
                    target=self._run_control_server, daemon=True, name='plc-control-api'
                )
                self._control_server_thread.start()
            else:
                logger.warning("Flask not available; HTTP control API disabled")

            # Give server time to start
            time.sleep(1)

            logger.info(f"CIP PLC started on {self.ip}:{self.port} in {self.mode.value} mode")
            logger.info(f"Available tags: {', '.join(self.tag_manager.list_tags())}")

        except Exception as e:
            logger.error(f"Error starting CIP PLC: {e}", exc_info=True)
            self.running = False
            raise

    def _run_server(self):
        """Run the cpppo server with automatic restart on crash.

        enip_main() can crash under load (rapid mode changes, concurrent connections).
        This method restarts it automatically with exponential backoff so the PLC
        continues generating tag values regardless of transient failures.
        """
        try:
            import cpppo.server.enip.main as enip_main_module

            if not hasattr(enip_main_module, 'main'):
                raise AttributeError("cpppo.server.enip.main module has no 'main' attribute")
            enip_main = enip_main_module.main

            if not callable(enip_main):
                raise TypeError(f"enip_main is not callable, it's a {type(enip_main)}")

            # Set global tag manager BEFORE creating attributes (persists across restarts)
            set_global_tag_manager(self.tag_manager)

            # Build tag definitions for cpppo once — shared across all restart attempts
            cpppo_tag_defs = {}
            for tag_name in self.tag_manager.list_tags():
                tag_info = self.tag_manager.get_tag_info(tag_name)
                tag_type = tag_info["type"]
                if tag_type == "BOOL":
                    cpppo_type = "BOOL"
                elif tag_type in ["INT", "DINT"]:
                    cpppo_type = "DINT"
                elif tag_type == "REAL":
                    cpppo_type = "REAL"
                else:
                    cpppo_type = "DINT"
                cpppo_tag_defs[tag_name] = (cpppo_type, 1)  # Scalar tags

            address = f"{self.ip}:{self.port}"

            # Build cpppo tag args in cpppo CLI format (e.g. "Motor_Speed=DINT")
            tag_args = []
            for tag_name, (tag_type, count) in cpppo_tag_defs.items():
                if count > 1:
                    tag_args.append(f"{tag_name}={tag_type}[{count}]")
                else:
                    tag_args.append(f"{tag_name}={tag_type}")

            # cpppo reads sys.argv internally (not only through the args= parameter),
            # so we must set sys.argv to the cpppo-compatible form before each call.
            # The original argv is restored in the finally block below.
            import sys
            original_argv = sys.argv
            cpppo_argv = [
                'cip_plc.py',
                '--address', address,
                '--print',
                '-v',
            ] + tag_args

            logger.info(f"CIP PLC server starting with cpppo on {address}")
            logger.info(f"Tags: {list(cpppo_tag_defs.keys())}")
            logger.info("Waiting for connections...")

            restart_delay = 2.0
            restart_count = 0
            max_restarts = 20

            try:
                while self.running:
                    try:
                        if restart_count > 0:
                            logger.info(
                                f"CIP PLC server restarting (attempt {restart_count + 1}/{max_restarts})"
                            )
                            set_global_tag_manager(self.tag_manager)

                        sys.argv = cpppo_argv
                        enip_main(attribute_class=ModeAwareAttribute, args=sys.argv[1:])

                        # enip_main returned without raising — only expected during shutdown
                        if not self.running:
                            logger.info("cpppo server stopped cleanly")
                            break
                        # Still running but enip_main exited — treat as a crash
                        raise RuntimeError("enip_main returned unexpectedly while server is running")

                    except KeyboardInterrupt:
                        logger.info("CIP PLC server interrupted")
                        self.running = False
                        break

                    except (SystemExit, Exception) as e:
                        # Any exit while self.running is True is treated as a crash.
                        # cpppo calls sys.exit() (SystemExit) on protocol errors, socket
                        # resets, or unexpected client behaviour — not just clean shutdowns.
                        # KeyboardInterrupt is handled separately above.
                        if not self.running:
                            # Server was asked to stop; the exit is expected
                            exit_code = e.code if isinstance(e, SystemExit) else None
                            logger.info(f"cpppo server stopped (exit={exit_code})")
                            break

                        restart_count += 1
                        exit_info = (
                            f"sys.exit({e.code})" if isinstance(e, SystemExit) else str(e)
                        )
                        if restart_count >= max_restarts:
                            logger.error(
                                f"CIP PLC server failed {restart_count} times, giving up. "
                                f"Last exit: {exit_info}"
                            )
                            self.running = False
                            break

                        logger.error(
                            f"CIP PLC server stopped unexpectedly ({exit_info}). "
                            f"Restarting in {restart_delay:.1f}s "
                            f"(attempt {restart_count}/{max_restarts})"
                        )
                        # Interruptible sleep — exits early if self.running is cleared
                        waited = 0.0
                        while waited < restart_delay and self.running:
                            time.sleep(0.5)
                            waited += 0.5
                        restart_delay = min(restart_delay * 1.5, 30.0)
            finally:
                sys.argv = original_argv

        except KeyboardInterrupt:
            logger.info("CIP PLC server interrupted during setup")
            self.running = False
        except Exception as e:
            logger.error(f"Fatal server setup error: {e}", exc_info=True)
            self.running = False

    def stop(self):
        """Stop the CIP PLC server."""
        self.running = False
        if self.server_thread:
            self.server_thread.join(timeout=5.0)
        if self.watchdog_thread:
            self.watchdog_thread.join(timeout=2.0)
        if self.stats_logger_thread:
            self.stats_logger_thread.join(timeout=2.0)
        logger.info("CIP PLC stopped")

    def _watchdog_thread(self):
        """Watchdog thread to monitor server health."""
        last_log = time.time()
        while self.running:
            time.sleep(5)  # Check every 5 seconds
            if not self.running:
                break
            current_time = time.time()

            # Check whether the CIP server thread is still alive
            if self.server_thread and not self.server_thread.is_alive():
                logger.warning(
                    "CIP PLC watchdog: server thread has exited "
                    "(restart loop in _run_server will handle recovery if running=True)"
                )

            # Periodic health log every 30 seconds
            elapsed = current_time - last_log
            if elapsed >= 30:
                alive = self.server_thread.is_alive() if self.server_thread else False
                logger.debug(
                    f"CIP PLC watchdog: server_thread alive={alive}, "
                    f"mode={self.tag_manager.mode.value}, "
                    f"reads={self.tag_manager.read_count}"
                )
                last_log = current_time

    def _stats_logger_thread(self):
        """Periodic statistics logging."""
        while self.running:
            time.sleep(30)  # Log stats every 30 seconds
            if not self.running:
                break
            try:
                stats = self.get_statistics()
                logger.info(f"CIP PLC stats: {stats}")
            except Exception as e:
                logger.warning(f"Error getting CIP PLC statistics: {e}")

    def build_control_app(self) -> 'Flask':
        """Build the Flask control API application.

        Returns:
            Configured Flask app for the control API
        """
        control_app = Flask(__name__ + '.control')

        plc_ref = self  # Capture reference for closures

        @control_app.route('/health', methods=['GET'])
        def health():
            return jsonify({'status': 'ok', 'mode': plc_ref.mode.value})

        @control_app.route('/mode', methods=['GET'])
        def get_mode():
            return jsonify({'mode': plc_ref.mode.value})

        @control_app.route('/mode', methods=['PUT'])
        def set_mode_endpoint():
            data = request.get_json(silent=True) or {}
            mode_str = data.get('mode', '')
            try:
                new_mode = OperatingMode(mode_str)
            except ValueError:
                valid = [m.value for m in OperatingMode]
                return jsonify({'error': f"Invalid mode '{mode_str}'. Valid: {valid}"}), 400
            plc_ref.set_mode(new_mode)
            return jsonify({'mode': plc_ref.mode.value})

        @control_app.route('/reset', methods=['POST'])
        def reset_mode():
            plc_ref.set_mode(OperatingMode.NORMAL)
            return jsonify({'mode': plc_ref.mode.value})

        return control_app

    def _run_control_server(self):
        """Run the HTTP control API server."""
        try:
            from werkzeug.serving import run_simple
            control_app = self.build_control_app()
            logger.info(f"CIP PLC control API starting on 0.0.0.0:{self.control_port}")
            run_simple('0.0.0.0', self.control_port, control_app,
                       threaded=True, use_reloader=False)
        except Exception as e:
            logger.error(f"Control API server error: {e}", exc_info=True)

    def set_mode(self, mode: OperatingMode):
        """Change operating mode.

        Args:
            mode: New operating mode
        """
        self.mode = mode
        self.tag_manager.set_mode(mode)
        logger.info(f"Operating mode changed to {mode.value}")

    def get_statistics(self):
        """Get server statistics.

        Returns:
            Dictionary with statistics
        """
        stats = self.tag_manager.get_statistics()
        stats.update({
            "running": self.running,
            "ip": self.ip,
            "port": self.port,
            "active_connections": len(self.connection_manager.connections)
        })
        return stats


def main():
    """Main entry point for CIP PLC simulator."""
    if not CPPPO_AVAILABLE:
        logger.error("cpppo is required but not installed.")
        logger.error("Please install dependencies from requirements.txt or see documentation for setup instructions.")
        return

    parser = argparse.ArgumentParser(description="CIP-Compatible Mock PLC Simulator")
    parser.add_argument("--ip", default="0.0.0.0", help="IP address to bind to")
    parser.add_argument("--port", type=int, default=44818, help="Port to listen on")
    parser.add_argument("--control-port", type=int, default=18080,
                        help="Port for HTTP control API (default: 18080)")
    parser.add_argument("--mode", choices=["normal", "degraded", "failed", "unresponsive"],
                     default="normal", help="Operating mode")

    args = parser.parse_args()

    mode = OperatingMode(args.mode)
    cip_plc = CIPPLC(ip=args.ip, port=args.port, mode=mode, control_port=args.control_port)

    try:
        cip_plc.start()

        # Keep running
        logger.info("CIP PLC running. Press Ctrl+C to stop.")
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
        cip_plc.stop()
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        cip_plc.stop()


if __name__ == "__main__":
    main()
