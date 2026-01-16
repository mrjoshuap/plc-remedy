"""Full CIP protocol-compatible PLC simulator using cpppo."""
import argparse
import logging
import os
import threading
import time
from typing import Optional

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

# Set logging level for all relevant modules
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Also set DEBUG for cpppo-related modules
logging.getLogger('cpppo').setLevel(logging.DEBUG)
logging.getLogger('mock.cip_objects').setLevel(logging.DEBUG)
logging.getLogger('mock.cip_services').setLevel(logging.DEBUG)
logging.getLogger('mock.tag_manager').setLevel(logging.DEBUG)
# Handle relative import paths
logging.getLogger('cip_objects').setLevel(logging.DEBUG)
logging.getLogger('cip_services').setLevel(logging.DEBUG)
logging.getLogger('tag_manager').setLevel(logging.DEBUG)


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
        
        logger.debug(f"ModeAwareAttribute.__getitem__ called for {self.tag_name} with key={key}")
        
        if _global_tag_manager is None:
            logger.warning(f"Tag manager not set for {self.tag_name}")
            default_value = 0 if not isinstance(key, slice) else [0]
            logger.debug(f"Returning default value {default_value} for {self.tag_name} (no tag manager)")
            return default_value
        
        try:
            logger.debug(f"Retrieving tag value for {self.tag_name} from tag manager")
            value = _global_tag_manager.get_tag_value(self.tag_name)
            logger.debug(f"Attribute read {self.tag_name}: {value} (type: {type(value).__name__})")
            
            # If key is a slice, return a list (cpppo expects iterable for slices)
            if isinstance(key, slice):
                # Return a list with the value (for scalar tags, just one element)
                result = [value]
                logger.debug(f"Returning slice result for {self.tag_name}: {result}")
                return result
            else:
                # Single index access, return the value directly
                logger.debug(f"Returning single value for {self.tag_name}: {value}")
                return value
        except KeyError:
            logger.warning(f"Tag {self.tag_name} not found in tag manager")
            default_value = 0 if not isinstance(key, slice) else [0]
            logger.debug(f"Returning default value {default_value} for {self.tag_name} (KeyError)")
            return default_value
        except Exception as e:
            logger.error(f"Error reading tag {self.tag_name}: {e}", exc_info=True)
            default_value = 0 if not isinstance(key, slice) else [0]
            logger.debug(f"Returning default value {default_value} for {self.tag_name} (exception)")
            return default_value
    
    def __setitem__(self, key, value):
        """Set tag value."""
        global _global_tag_manager
        
        logger.debug(f"ModeAwareAttribute.__setitem__ called for {self.tag_name} with key={key}, value={value} (type: {type(value).__name__})")
        
        if _global_tag_manager is None:
            logger.warning(f"Tag manager not set for {self.tag_name}")
            return
        
        try:
            logger.debug(f"Setting tag value for {self.tag_name} via tag manager")
            _global_tag_manager.set_tag_value(self.tag_name, value)
            logger.debug(f"Attribute write {self.tag_name}: {value} (type: {type(value).__name__}) - success")
        except Exception as e:
            logger.error(f"Failed to set tag {self.tag_name}: {e}", exc_info=True)


class CIPPLC:
    """Full CIP protocol-compatible PLC simulator."""
    
    def __init__(self, ip: str = "0.0.0.0", port: int = 44818, 
                 mode: OperatingMode = OperatingMode.NORMAL):
        """Initialize CIP PLC simulator.
        
        Args:
            ip: IP address to bind to
            port: Port to listen on (CIP default is 44818)
            mode: Operating mode
        """
        if not CPPPO_AVAILABLE:
            raise ImportError("cpppo is required. Please install dependencies from requirements.txt or see documentation for setup instructions.")
        
        self.ip = ip
        self.port = port
        self.mode = mode
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
            
            # Give server time to start
            time.sleep(1)
            
            logger.info(f"CIP PLC started on {self.ip}:{self.port} in {self.mode.value} mode")
            logger.info(f"Available tags: {', '.join(self.tag_manager.list_tags())}")
            
        except Exception as e:
            logger.error(f"Error starting CIP PLC: {e}", exc_info=True)
            self.running = False
            raise
    
    def _run_server(self):
        """Run the cpppo server (internal)."""
        try:
            # Try different import approaches to find the correct main function
            import sys
            
            # Import the main module first, then get the main function from it
            import cpppo.server.enip.main as enip_main_module
            
            # Get the main function from the module
            if hasattr(enip_main_module, 'main'):
                enip_main = enip_main_module.main
            else:
                # If no 'main' attribute, the module itself might be callable (unlikely but handle it)
                raise AttributeError("cpppo.server.enip.main module has no 'main' attribute")
            
            # Final verification
            if not callable(enip_main):
                raise TypeError(f"enip_main is not callable, it's a {type(enip_main)}")
            
            # Set global tag manager BEFORE creating attributes
            set_global_tag_manager(self.tag_manager)
            
            # Build tag definitions for cpppo
            # Format: name -> (CIP_type_string, count)
            cpppo_tag_defs = {}
            for tag_name in self.tag_manager.list_tags():
                tag_info = self.tag_manager.get_tag_info(tag_name)
                tag_type = tag_info["type"]
                
                # Map to cpppo type strings
                if tag_type == "BOOL":
                    cpppo_type = "BOOL"
                elif tag_type in ["INT", "DINT"]:
                    cpppo_type = "DINT"
                elif tag_type == "REAL":
                    cpppo_type = "REAL"
                else:
                    cpppo_type = "DINT"
                
                cpppo_tag_defs[tag_name] = (cpppo_type, 1)  # Scalar tags
            
            # Build address string
            address = f"{self.ip}:{self.port}"
            
            # Prepare arguments for enip_main
            # cpppo expects tags as command-line arguments in format: TAG=TYPE[count]
            # e.g., Light_Status=BOOL, Motor_Speed=DINT
            original_argv = sys.argv
            try:
                # Build tag arguments in cpppo format
                tag_args = []
                for tag_name, (tag_type, count) in cpppo_tag_defs.items():
                    if count > 1:
                        tag_args.append(f"{tag_name}={tag_type}[{count}]")
                    else:
                        tag_args.append(f"{tag_name}={tag_type}")
                
                sys.argv = [
                    'cip_plc.py',
                    '--address', address,
                    '--print',  # Print I/O access for debugging
                    '-v',  # Verbose logging
                ] + tag_args  # Add tag definitions as command-line arguments
                
                logger.info(f"CIP PLC server starting with cpppo on {address}")
                logger.info(f"Tags: {list(cpppo_tag_defs.keys())}")
                logger.info("Waiting for connections...")
                
                # Run cpppo server with ModeAwareAttribute class
                # enip_main will parse sys.argv and create ModeAwareAttribute instances with (name, parser) signature
                # Note: enip_main is a blocking call - if it hangs, the server thread will appear stuck
                try:
                    logger.debug("Calling enip_main - this is a blocking call")
                    enip_main(
                        attribute_class=ModeAwareAttribute,
                        args=sys.argv[1:]  # Pass all args including tag definitions
                    )
                    logger.info("enip_main returned (server stopped normally)")
                except Exception as e:
                    logger.error(f"enip_main raised an exception: {e}", exc_info=True)
                    raise
            finally:
                sys.argv = original_argv
            
        except KeyboardInterrupt:
            logger.info("CIP PLC server interrupted")
            self.running = False
        except Exception as e:
            logger.error(f"Server thread error: {e}", exc_info=True)
            import traceback
            traceback.print_exc()
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
            # Log periodic health check every 30 seconds
            elapsed = current_time - last_log
            if elapsed >= 30:
                logger.debug("CIP PLC watchdog: server process appears responsive")
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
    parser.add_argument("--mode", choices=["normal", "degraded", "failed", "unresponsive"],
                     default="normal", help="Operating mode")
    
    args = parser.parse_args()
    
    mode = OperatingMode(args.mode)
    cip_plc = CIPPLC(ip=args.ip, port=args.port, mode=mode)
    
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
