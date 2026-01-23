"""PLC communication client using pycomm3 for Allen-Bradley CIP protocol."""
import logging
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from pycomm3 import LogixDriver
from pycomm3.exceptions import CommError, RequestError, BufferEmptyError
from pycomm3.cip.data_types import DataTypes

from app.models import TagResult, ConnectionStats
from app.config import PLCConfig, TagConfig

logger = logging.getLogger(__name__)


class PLCClient:
    """Client for communicating with Allen-Bradley PLCs via CIP protocol."""

    def __init__(self, config: PLCConfig, tags_config: Optional[Dict[str, TagConfig]] = None):
        """Initialize PLC client.

        Args:
            config: PLC configuration
            tags_config: Optional tags configuration dict (for mock mode tag population)
        """
        self.config = config
        self._tags_config = tags_config or {}
        self._driver: Optional[LogixDriver] = None
        self._lock = threading.Lock()
        self._read_lock = threading.Lock()  # Lock for serializing read operations
        self._stats = ConnectionStats(
            connected=False,
            connection_start_time=None
        )
        self._last_error: Optional[str] = None

    def connect(self) -> bool:
        """Establish connection to PLC.

        Returns:
            True if connection successful, False otherwise
        """
        # Check if already connected (brief lock)
        with self._lock:
            if self._driver is not None and self._driver.connected:
                logger.debug("PLC already connected")
                return True

        # Perform connection OUTSIDE lock to avoid blocking other operations
        try:
            logger.info(f"Connecting to PLC at {self.config.ip_address} (slot {self.config.slot})")

            # In mock mode, disable tag list upload to avoid MSP during initialization
            # We'll manually populate tags from config instead
            init_tags = not self.config.mock_mode
            init_program_tags = not self.config.mock_mode

            driver = LogixDriver(
                self.config.ip_address,
                slot=self.config.slot,
                timeout=self.config.timeout,
                init_tags=init_tags,
                init_program_tags=init_program_tags
            )

            # Set micro800 override if mock_mode is enabled (independent of protocol_mode)
            if self.config.mock_mode:
                if hasattr(driver, '_micro800'):
                    driver._micro800 = True
                if hasattr(driver, '_cfg'):
                    driver._cfg['micro800'] = True
                logger.info("Set Micro800 override (mock_mode enabled)")

            # Determine protocol mode behavior
            if self.config.protocol_mode == "serial":
                # Force Micro800 mode to disable MSP and use serial methods
                if hasattr(driver, '_micro800'):
                    driver._micro800 = True
                if hasattr(driver, '_cfg'):
                    driver._cfg['micro800'] = True
                logger.info("Forcing Micro800 mode (protocol_mode=serial, using serial methods)")
            else:
                # protocol_mode == "default" - use pycomm3 default logic
                logger.info(f"Using pycomm3 default protocol logic (protocol_mode=default, mock_mode={self.config.mock_mode})")

            # Open connection (this is a blocking network operation)
            driver.open()

            # Update state inside lock
            with self._lock:
                self._driver = driver

                if driver.connected:
                    # In mock mode, populate tags from config since we disabled tag list upload
                    if self.config.mock_mode:
                        self._populate_tags_from_config()

                    self._stats.connected = True
                    self._stats.connection_start_time = datetime.now()
                    self._stats.last_successful_read = datetime.now()
                    logger.info(f"Successfully connected to PLC at {self.config.ip_address} (protocol_mode={self.config.protocol_mode}, mock_mode={self.config.mock_mode})")
                    return True
                else:
                    logger.error("Failed to connect to PLC: driver reports not connected")
                    self._driver = None
                    self._stats.connected = False
                    return False

        except (CommError, RequestError, Exception) as e:
                error_msg = str(e)
                error_lower = error_msg.lower()
                error_type = type(e).__name__

                # In mock mode, handle Multiple Service Packet errors gracefully
                # These errors occur when the mock PLC doesn't support certain CIP services
                # but the connection can still be used for basic tag operations
                if self.config.mock_mode and (
                    "service not supported" in error_lower or
                    "multiple service" in error_lower or
                    "0x08" in error_msg or  # CIP error code 0x08 = Service Not Supported
                    ("connection" in error_lower and "closed" in error_lower) or
                    "buffemptyerror" in error_lower or  # BufferEmptyError from pycomm3
                    error_type == "BufferEmptyError" or
                    "failed to get attribute list" in error_lower or
                    "failed to parse reply" in error_lower or
                    "tag doesn't exist" in error_lower
                ):
                    # Check if we can still use the connection despite the error
                    # Sometimes pycomm3 closes the connection on these errors, but we can reconnect
                    logger.warning(
                        f"Mock PLC connection error (handled gracefully): {error_msg[:200]}. "
                        "This is expected with mock PLCs that don't support all CIP services. "
                        "Attempting to continue..."
                    )

                    # Try to check if connection is still usable
                    with self._lock:
                        try:
                            if self._driver is not None and hasattr(self._driver, 'connected'):
                                if self._driver.connected:
                                    # Connection is still open, use it
                                    # Manually populate _tags if tag list upload failed
                                    self._populate_tags_from_config()
                                    self._stats.connected = True
                                    self._stats.connection_start_time = datetime.now()
                                    self._stats.last_successful_read = datetime.now()
                                    logger.info("Connection usable despite error - continuing in mock mode")
                                    return True
                        except Exception:
                            pass

                        # Connection closed, but in mock mode we'll allow retries
                        # Don't treat this as a fatal error
                        logger.info("Connection closed due to unsupported service, but mock mode allows retries")
                        if self._driver is not None:
                            self._driver = None
                        self._stats.connected = False
                        self._last_error = f"Mock PLC limitation: {error_msg[:200]}"
                        return False

                # For real PLCs or non-mock-mode, treat all errors as fatal
                error_msg = f"PLC connection error: {error_msg}"
                logger.error(error_msg)
                with self._lock:
                    if self._driver is not None:
                        self._driver = None
                    self._stats.connected = False
                    self._stats.total_errors += 1
                    self._stats.last_error = error_msg
                return False

    def disconnect(self) -> None:
        """Close connection to PLC."""
        # Get driver reference outside lock to avoid blocking
        with self._lock:
            if self._driver is None:
                return
            driver = self._driver
            self._driver = None  # Clear reference immediately to prevent new operations
            self._stats.connected = False

        # Close connection outside lock to avoid blocking
        try:
            if driver.connected:
                driver.close()
            logger.info("Disconnected from PLC")
        except Exception as e:
            logger.warning(f"Error during PLC disconnect: {e}")

    def is_connected(self) -> bool:
        """Check if connected to PLC.

        Returns:
            True if connected, False otherwise
        """
        with self._lock:
            if self._driver is None:
                return False
            try:
                return self._driver.connected
            except Exception:
                return False

    def check_connection_health(self) -> bool:
        """Check if the PLC connection is still alive without blocking.

        This is a lightweight check that doesn't perform a full read operation.

        Returns:
            True if connection appears healthy, False otherwise
        """
        with self._lock:
            if self._driver is None:
                return False
            # Check if driver reports connected status
            try:
                return self._driver.connected
            except Exception as e:
                logger.debug(f"Connection health check failed: {e}")
                return False

    def _populate_tags_from_config(self) -> None:
        """Manually populate pycomm3's _tags dictionary from config.

        This is used in mock mode when tag list upload fails.
        Allows pycomm3 to read tags even without successful tag list upload.
        """
        if not self.config.mock_mode or self._driver is None:
            return

        if not self._tags_config:
            logger.debug("No tags config provided, skipping manual tag population")
            return

        try:
            # Map config types to pycomm3 data type names and type classes
            # Use DataTypes.get() to get the type class for each data type
            type_mapping = {
                'bool': ('BOOL', DataTypes.get('BOOL')),
                'int': ('DINT', DataTypes.get('DINT')),
                'float': ('REAL', DataTypes.get('REAL')),
                'real': ('REAL', DataTypes.get('REAL')),
                'dint': ('DINT', DataTypes.get('DINT')),
            }

            # Disable instance IDs to use tag names directly
            if hasattr(self._driver, '_cfg'):
                self._driver._cfg['use_instance_ids'] = False

            # Initialize _tags if it doesn't exist
            if not hasattr(self._driver, '_tags') or self._driver._tags is None:
                self._driver._tags = {}

            # Populate _tags from config
            for config_key, tag_config in self._tags_config.items():
                # Handle both TagConfig objects and dicts
                if hasattr(tag_config, 'name'):
                    tag_name = tag_config.name
                    tag_type = tag_config.type if hasattr(tag_config, 'type') else 'DINT'
                elif isinstance(tag_config, dict):
                    tag_name = tag_config.get('name', config_key)
                    tag_type = tag_config.get('type', 'DINT')
                else:
                    tag_name = config_key
                    tag_type = 'DINT'

                pycomm3_type_name, type_class = type_mapping.get(tag_type.lower(), ('DINT', DataTypes.get('DINT')))

                self._driver._tags[tag_name] = {
                    'tag_name': tag_name,
                    'instance_id': 0,  # Mock PLC doesn't use instance IDs
                    'tag_type': 'atomic',  # Assume atomic tags for simplicity
                    'data_type': pycomm3_type_name,  # Required: same as data_type_name for atomic
                    'data_type_name': pycomm3_type_name,
                    'external_access': 'Read/Write',
                    'dim': 0,  # Scalar tags (not arrays)
                    'dimensions': [0, 0, 0],  # Required: list of 3 ints
                    'alias': False,
                    'type_class': type_class  # Required: Python type class for encoding/decoding
                }

            logger.info(f"Manually populated {len(self._driver._tags)} tags from config for mock mode")
        except Exception as e:
            logger.warning(f"Failed to populate tags from config: {e}")

    def read_tag(self, tag_name: str) -> TagResult:
        """Read a single tag from the PLC.

        Args:
            tag_name: Name of the tag to read

        Returns:
            TagResult with value or error information
        """
        timestamp = datetime.now()

        # Ensure connection
        if not self.is_connected():
            if not self.connect():
                error_msg = "Not connected to PLC and connection attempt failed"
                with self._lock:
                    self._stats.total_errors += 1
                    self._stats.last_error = error_msg
                return TagResult(
                    tag_name=tag_name,
                    value=None,
                    timestamp=timestamp,
                    success=False,
                    error=error_msg
                )

        # Get driver reference (brief lock to ensure it's not None)
        with self._lock:
            if self._driver is None:
                error_msg = "PLC driver not initialized"
                self._stats.total_errors += 1
                self._stats.last_error = error_msg
                return TagResult(
                    tag_name=tag_name,
                    value=None,
                    timestamp=timestamp,
                    success=False,
                    error=error_msg
                )
            # Get reference to driver (we'll use it outside the lock)
            driver = self._driver

        # Serialize read operations to prevent overwhelming the PLC
        # Acquire read lock to ensure only one read happens at a time
        try:
            with self._read_lock:
                # Check connection health before attempting read
                if not self.check_connection_health():
                    logger.warning(f"Connection health check failed before reading tag '{tag_name}', attempting reconnect")
                    # Connection appears dead, try to reconnect
                    if not self.connect():
                        error_msg = "Connection health check failed and reconnect attempt failed"
                        with self._lock:
                            self._stats.total_errors += 1
                            self._stats.last_error = error_msg
                        return TagResult(
                            tag_name=tag_name,
                            value=None,
                            timestamp=timestamp,
                            success=False,
                            error=error_msg
                        )
                    # Re-check after reconnect
                    with self._lock:
                        driver = self._driver
                    if driver is None:
                        error_msg = "PLC driver not available after reconnect"
                        with self._lock:
                            self._stats.total_errors += 1
                            self._stats.last_error = error_msg
                        return TagResult(
                            tag_name=tag_name,
                            value=None,
                            timestamp=timestamp,
                            success=False,
                            error=error_msg
                        )

                # Perform read with explicit timeout awareness
                # The LogixDriver should use self.config.timeout, but we'll catch timeout-related errors
                read_start_time = time.time()
                try:
                    result = driver.read(tag_name)
                    read_duration = time.time() - read_start_time
                    if read_duration > 0.5:  # Log if read takes more than 500ms
                        logger.warning(f"PLC read for '{tag_name}' took {read_duration:.3f} seconds (slow, >500ms)")
                    elif read_duration > 0.2:  # Log if read takes more than 200ms (moderate)
                        logger.debug(f"PLC read for '{tag_name}' took {read_duration:.3f} seconds")
                except Exception as read_error:
                    read_duration = time.time() - read_start_time
                    logger.error(f"PLC read for '{tag_name}' failed after {read_duration:.3f} seconds: {read_error}")
                    raise

                # Update statistics INSIDE the lock
                with self._lock:
                    if result.error:
                        error_msg = f"Tag read error: {result.error}"
                        logger.warning(f"Failed to read tag '{tag_name}': {error_msg}")
                        self._stats.total_errors += 1
                        self._stats.last_error = error_msg
                        return TagResult(
                            tag_name=tag_name,
                            value=None,
                            timestamp=timestamp,
                            success=False,
                            error=error_msg
                        )

                    # Success
                    self._stats.total_reads += 1
                    self._stats.last_successful_read = timestamp
                    logger.debug(f"Read tag '{tag_name}': {result.value}")

                    return TagResult(
                        tag_name=tag_name,
                        value=result.value,
                        timestamp=timestamp,
                        success=True,
                        error=None
                    )

        except (CommError, RequestError, BufferEmptyError) as e:
            error_msg = str(e)
            error_lower = error_msg.lower()
            error_type = type(e).__name__

            # Update statistics inside lock
            with self._lock:
                # In mock mode, handle service errors gracefully
                # This includes "Tag doesn't exist" errors when tag list upload failed
                if self.config.mock_mode and (
                    "service not supported" in error_lower or
                    "multiple service" in error_lower or
                    "0x08" in error_msg or
                    error_type == "BufferEmptyError" or
                    "buffemptyerror" in error_lower or
                    "failed to parse reply" in error_lower or
                    "failed to get attribute list" in error_lower or
                    "tag doesn't exist" in error_lower or
                    "tag doesn't exist" in error_msg or
                    "failed to parse tag request" in error_lower
                ):
                    # This is a known limitation of mock PLCs
                    # When tag list upload fails, pycomm3 doesn't know about tags
                    # but the tags still exist in the mock PLC
                    logger.debug(
                        f"Mock PLC service error for tag '{tag_name}' (handled gracefully): {error_msg[:200]}"
                    )
                    # Don't mark connection as lost for service errors in mock mode
                    # The connection might still be usable for other operations
                    self._stats.total_errors += 1
                    self._stats.last_error = f"Mock PLC limitation: {error_msg[:200]}"
                    return TagResult(
                        tag_name=tag_name,
                        value=None,
                        timestamp=timestamp,
                        success=False,
                        error=f"Mock PLC service not supported: {error_msg[:200]}"
                    )

                # For real errors or non-mock-mode, treat as connection failure
                error_msg = f"PLC communication error reading tag '{tag_name}': {error_msg}"
                logger.error(error_msg)
                self._stats.connected = False  # Assume connection lost
                self._stats.total_errors += 1
                self._stats.last_error = error_msg
                return TagResult(
                    tag_name=tag_name,
                    value=None,
                    timestamp=timestamp,
                    success=False,
                    error=error_msg
                )
        except Exception as e:
            error_msg = f"Unexpected error reading tag '{tag_name}': {str(e)}"
            logger.error(error_msg, exc_info=True)
            with self._lock:
                self._stats.total_errors += 1
                self._stats.last_error = error_msg
            return TagResult(
                tag_name=tag_name,
                value=None,
                timestamp=timestamp,
                success=False,
                error=error_msg
            )

    def read_tags(self, tag_names: List[str]) -> Dict[str, TagResult]:
        """Read multiple tags from the PLC using individual single-tag reads.

        This method reads tags sequentially. When protocol_mode is "serial",
        this avoids Multiple Service Packets (MSP). When protocol_mode is "default",
        pycomm3 may use MSP internally for other operations, but tag reads are
        still performed sequentially.

        Args:
            tag_names: List of tag names to read

        Returns:
            Dictionary mapping tag names to TagResult objects
        """
        results = {}

        # Read tags sequentially to avoid overwhelming the PLC
        # The read_lock in read_tag() ensures only one read happens at a time
        # When protocol_mode is "serial", this avoids Multiple Service Packets (MSP)
        for i, tag_name in enumerate(tag_names):
            logger.debug(f"Reading tag: {tag_name}")
            result = self.read_tag(tag_name)
            # Use the tag_name from the result (which should match the input)
            results[result.tag_name] = result
            logger.debug(f"Stored result for {result.tag_name}: success={result.success}, value={result.value if result.success else result.error}")

            # Small delay between reads to prevent overwhelming the PLC
            # Only delay if there are more tags to read
            if i < len(tag_names) - 1:  # Don't delay after the last tag
                time.sleep(0.05)  # 50ms delay between reads

        logger.debug(f"read_tags returning {len(results)} results: {list(results.keys())}")
        return results

    def write_tag(self, tag_name: str, value: Any) -> bool:
        """Write a value to a PLC tag.

        Args:
            tag_name: Name of the tag to write
            value: Value to write

        Returns:
            True if write successful, False otherwise
        """
        # Ensure connection
        if not self.is_connected():
            if not self.connect():
                logger.error("Cannot write tag: not connected to PLC")
                return False

        # Get driver reference (brief lock to ensure it's not None)
        with self._lock:
            if self._driver is None:
                error_msg = "PLC driver not initialized"
                self._stats.total_errors += 1
                self._stats.last_error = error_msg
                return False
            # Get reference to driver (we'll use it outside the lock)
            driver = self._driver

        # Perform network I/O OUTSIDE the lock to avoid blocking API requests
        try:
            result = driver.write(tag_name, value)

            # Update statistics INSIDE the lock
            with self._lock:
                if result.error:
                    error_msg = f"Tag write error: {result.error}"
                    logger.error(f"Failed to write tag '{tag_name}': {error_msg}")
                    self._stats.total_errors += 1
                    self._stats.last_error = error_msg
                    return False

                logger.info(f"Wrote tag '{tag_name}': {value}")
                return True

        except (CommError, RequestError, BufferEmptyError) as e:
            error_msg = str(e)
            error_lower = error_msg.lower()
            error_type = type(e).__name__

            # Update statistics inside lock
            with self._lock:
                # In mock mode, handle service errors gracefully
                # This includes "Tag doesn't exist" errors when tag list upload failed
                if self.config.mock_mode and (
                    "service not supported" in error_lower or
                    "multiple service" in error_lower or
                    "0x08" in error_msg or
                    error_type == "BufferEmptyError" or
                    "buffemptyerror" in error_lower or
                    "failed to parse reply" in error_lower or
                    "failed to get attribute list" in error_lower or
                    "tag doesn't exist" in error_lower or
                    "tag doesn't exist" in error_msg or
                    "failed to parse tag request" in error_lower
                ):
                    logger.debug(
                        f"Mock PLC service error writing tag '{tag_name}' (handled gracefully): {error_msg[:200]}"
                    )
                    # Don't mark connection as lost for service errors in mock mode
                    self._stats.total_errors += 1
                    self._stats.last_error = f"Mock PLC limitation: {error_msg[:200]}"
                    return False

                # For real errors or non-mock-mode, treat as connection failure
                error_msg = f"PLC communication error writing tag '{tag_name}': {error_msg}"
                logger.error(error_msg)
                self._stats.connected = False
                self._stats.total_errors += 1
                self._stats.last_error = error_msg
                return False

        except Exception as e:
            error_msg = f"Unexpected error writing tag '{tag_name}': {str(e)}"
            logger.error(error_msg, exc_info=True)
            with self._lock:
                self._stats.total_errors += 1
                self._stats.last_error = error_msg
            return False

    def get_connection_stats(self) -> ConnectionStats:
        """Get connection statistics.

        Returns:
            ConnectionStats object with current statistics
        """
        with self._lock:
            # Check connection status directly (don't call is_connected() to avoid deadlock)
            connected = False
            if self._driver is not None:
                try:
                    connected = self._driver.connected
                except Exception:
                    connected = False
            self._stats.connected = connected

            return ConnectionStats(
                connected=self._stats.connected,
                last_successful_read=self._stats.last_successful_read,
                total_reads=self._stats.total_reads,
                total_errors=self._stats.total_errors,
                connection_start_time=self._stats.connection_start_time,
                last_error=self._stats.last_error
            )
