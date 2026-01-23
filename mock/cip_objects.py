"""CIP object definitions for mock PLC."""
import struct
import logging
from typing import Dict, Any, Optional
from cpppo.server.enip import device

logger = logging.getLogger(__name__)


# CIP Object Class IDs
CLASS_IDENTITY = 0x01
CLASS_MESSAGE_ROUTER = 0x02
CLASS_CONNECTION_MANAGER = 0x06
CLASS_ASSEMBLY = 0x04

# CIP Attribute IDs for Identity Object
ATTR_VENDOR_ID = 1
ATTR_DEVICE_TYPE = 2
ATTR_PRODUCT_CODE = 3
ATTR_REVISION = 4
ATTR_STATUS = 5
ATTR_SERIAL_NUMBER = 6
ATTR_PRODUCT_NAME = 7
ATTR_STATE = 8


class IdentityObject:
    """Device Identity Object (Class 0x01, Instance 0x01)."""

    def __init__(self):
        """Initialize identity object with Rockwell Automation values."""
        # Rockwell Automation vendor ID
        self.vendor_id = 1
        self.device_type = 0x0C  # Programmable Logic Controller
        self.product_code = 0xAB  # Mock product code
        self.revision_major = 1
        self.revision_minor = 0
        self.status = 0x0000  # Operational
        self.serial_number = 0x12345678
        self.product_name = b"Mock ControlLogix\x00"
        self.state = 0  # Non-existent

    def get_attribute(self, attribute_id: int) -> Optional[bytes]:
        """Get attribute value.

        Args:
            attribute_id: Attribute ID to retrieve

        Returns:
            Attribute value as bytes or None if not found
        """
        if attribute_id == ATTR_VENDOR_ID:
            return struct.pack("<H", self.vendor_id)
        elif attribute_id == ATTR_DEVICE_TYPE:
            return struct.pack("<H", self.device_type)
        elif attribute_id == ATTR_PRODUCT_CODE:
            return struct.pack("<H", self.product_code)
        elif attribute_id == ATTR_REVISION:
            return struct.pack("<BB", self.revision_major, self.revision_minor)
        elif attribute_id == ATTR_STATUS:
            return struct.pack("<H", self.status)
        elif attribute_id == ATTR_SERIAL_NUMBER:
            return struct.pack("<I", self.serial_number)
        elif attribute_id == ATTR_PRODUCT_NAME:
            return self.product_name
        elif attribute_id == ATTR_STATE:
            return struct.pack("<B", self.state)
        else:
            return None


class ConnectionManager:
    """Connection Manager Object (Class 0x06, Instance 0x01)."""

    def __init__(self):
        """Initialize connection manager."""
        self.connections: Dict[int, Dict[str, Any]] = {}
        self.next_connection_id = 0x1000
        self.next_connection_serial = 1

    def forward_open(self, request_data: bytes) -> tuple:
        """Handle Forward Open service (0x54).

        Args:
            request_data: Forward Open request data

        Returns:
            Tuple of (success: bool, response_data: bytes, connection_id_o_to_t: int, connection_id_t_to_o: int)
        """
        logger.debug(f"ConnectionManager.forward_open called - request data length: {len(request_data)}")
        logger.debug(f"Request data (hex): {request_data.hex() if request_data else 'empty'}")

        try:
            # Parse Forward Open request
            # This is a simplified parser - full implementation would parse all fields
            if len(request_data) < 50:
                logger.debug(f"Forward Open failed - insufficient data: {len(request_data)} bytes (need at least 50)")
                return (False, b"\x00", 0, 0)  # Error response

            # Extract connection IDs from request (simplified)
            # In real implementation, parse priority, timeout, RPI, etc.
            connection_id_o_to_t = self.next_connection_id
            connection_id_t_to_o = self.next_connection_id + 1
            self.next_connection_id += 2
            logger.debug(f"Allocated connection IDs - O->T: 0x{connection_id_o_to_t:04X}, T->O: 0x{connection_id_t_to_o:04X}")

            connection_serial = self.next_connection_serial
            self.next_connection_serial += 1
            logger.debug(f"Allocated connection serial: {connection_serial}")

            # Store connection info
            self.connections[connection_id_o_to_t] = {
                "o_to_t": connection_id_o_to_t,
                "t_to_o": connection_id_t_to_o,
                "serial": connection_serial,
                "state": "established"
            }
            logger.debug(f"Stored connection info - total connections: {len(self.connections)}")

            # Build Forward Open response
            # Response structure: Extended Status (2 bytes) + Connection IDs + Serial Number
            response = struct.pack("<H", 0x0000)  # Success status
            response += struct.pack("<I", connection_id_o_to_t)  # O->T Connection ID
            response += struct.pack("<I", connection_id_t_to_o)  # T->O Connection ID
            response += struct.pack("<H", connection_serial)  # Connection Serial Number

            logger.info(f"Forward Open successful: O->T={connection_id_o_to_t:04X}, T->O={connection_id_t_to_o:04X}, Serial={connection_serial}")
            logger.debug(f"Forward Open response length: {len(response)} bytes")
            return (True, response, connection_id_o_to_t, connection_id_t_to_o)

        except Exception as e:
            logger.error(f"Forward Open error: {e}", exc_info=True)
            return (False, struct.pack("<H", 0x0100), 0, 0)  # Error status

    def forward_close(self, connection_id: int) -> bool:
        """Handle Forward Close service.

        Args:
            connection_id: Connection ID to close

        Returns:
            True if successful
        """
        logger.debug(f"ConnectionManager.forward_close called - connection ID: 0x{connection_id:04X}")
        logger.debug(f"Current connections: {list(self.connections.keys())}")

        if connection_id in self.connections:
            connection_info = self.connections[connection_id]
            del self.connections[connection_id]
            logger.info(f"Forward Close: connection {connection_id:04X} closed (O->T: 0x{connection_info.get('o_to_t', 0):04X}, T->O: 0x{connection_info.get('t_to_o', 0):04X})")
            logger.debug(f"Remaining connections: {len(self.connections)}")
            return True
        else:
            logger.debug(f"Forward Close failed - connection 0x{connection_id:04X} not found in active connections")
            return False


class TagObject:
    """Tag Object for tag access."""

    def __init__(self, tag_manager):
        """Initialize tag object.

        Args:
            tag_manager: TagManager instance
        """
        self.tag_manager = tag_manager

    def read_tag(self, tag_path: bytes) -> tuple:
        """Read tag value.

        Args:
            tag_path: Tag path as bytes (CIP path format)

        Returns:
            Tuple of (success: bool, data_type: int, value: bytes)
        """
        logger.debug(f"TagObject.read_tag called - path length: {len(tag_path)}")
        logger.debug(f"Tag path (hex): {tag_path.hex() if tag_path else 'empty'}")

        try:
            # Parse tag path (simplified - assumes ASCII tag name)
            # Real implementation would parse full CIP path structure
            tag_name = tag_path.decode('ascii', errors='ignore').strip('\x00')
            logger.debug(f"Parsed tag name: '{tag_name}' (from {len(tag_path)} bytes)")

            if not tag_name or tag_name not in self.tag_manager.tags:
                logger.warning(f"Tag not found: '{tag_name}' (available tags: {list(self.tag_manager.tags.keys())})")
                return (False, 0, b"")

            # Get tag value
            logger.debug(f"Retrieving value for tag '{tag_name}' from tag manager")
            value = self.tag_manager.get_tag_value(tag_name)
            tag_info = self.tag_manager.get_tag_info(tag_name)
            tag_type = tag_info["type"]
            logger.debug(f"Tag '{tag_name}' value: {value} (type: {tag_type}, Python type: {type(value).__name__})")

            # Convert to CIP data type code and encode value
            cip_type_code, encoded_value = self._encode_value(tag_type, value)
            logger.debug(f"Encoded tag '{tag_name}': CIP type=0x{cip_type_code:02X}, encoded length={len(encoded_value)} bytes")

            logger.debug(f"Read tag {tag_name}: {value} (type: {tag_type}, CIP type: 0x{cip_type_code:02X}) - success")
            return (True, cip_type_code, encoded_value)

        except Exception as e:
            logger.error(f"Read tag error: {e}", exc_info=True)
            return (False, 0, b"")

    def write_tag(self, tag_path: bytes, data_type: int, value_data: bytes) -> bool:
        """Write tag value.

        Args:
            tag_path: Tag path as bytes
            data_type: CIP data type code
            value_data: Value data as bytes

        Returns:
            True if successful
        """
        logger.debug(f"TagObject.write_tag called - path length: {len(tag_path)}, data_type: 0x{data_type:02X}, value_data length: {len(value_data)}")
        logger.debug(f"Tag path (hex): {tag_path.hex() if tag_path else 'empty'}")

        try:
            # Parse tag path
            tag_name = tag_path.decode('ascii', errors='ignore').strip('\x00')
            logger.debug(f"Parsed tag name: '{tag_name}' (from {len(tag_path)} bytes)")

            if not tag_name or tag_name not in self.tag_manager.tags:
                logger.warning(f"Tag not found for write: '{tag_name}' (available tags: {list(self.tag_manager.tags.keys())})")
                return False

            # Decode value
            logger.debug(f"Decoding value for tag '{tag_name}' - CIP type: 0x{data_type:02X}, data length: {len(value_data)}")
            value = self._decode_value(data_type, value_data)
            logger.debug(f"Decoded value for tag '{tag_name}': {value} (Python type: {type(value).__name__})")

            # Set tag value
            logger.debug(f"Setting tag value for '{tag_name}' via tag manager")
            success = self.tag_manager.set_tag_value(tag_name, value)

            if success:
                logger.debug(f"Write tag {tag_name}: {value} (type: {type(value).__name__}) - success")
            else:
                logger.debug(f"Write tag {tag_name} failed - tag manager returned False")

            return success

        except Exception as e:
            logger.error(f"Write tag error: {e}", exc_info=True)
            return False

    def _encode_value(self, tag_type: str, value: Any) -> tuple:
        """Encode value to CIP format.

        Args:
            tag_type: Tag type string (BOOL, DINT, etc.)
            value: Value to encode

        Returns:
            Tuple of (cip_type_code: int, encoded_bytes: bytes)
        """
        if tag_type == "BOOL":
            return (0xC1, struct.pack("<?", bool(value)))
        elif tag_type == "INT":
            return (0xC2, struct.pack("<h", int(value)))
        elif tag_type == "DINT":
            return (0xC4, struct.pack("<i", int(value)))
        elif tag_type == "REAL":
            return (0xCA, struct.pack("<f", float(value)))
        else:
            # Default to DINT
            return (0xC4, struct.pack("<i", int(value)))

    def _decode_value(self, cip_type_code: int, data: bytes) -> Any:
        """Decode value from CIP format.

        Args:
            cip_type_code: CIP data type code
            data: Encoded value bytes

        Returns:
            Decoded value
        """
        if cip_type_code == 0xC1:  # BOOL
            return struct.unpack("<?", data[:1])[0]
        elif cip_type_code == 0xC2:  # INT
            return struct.unpack("<h", data[:2])[0]
        elif cip_type_code == 0xC4:  # DINT
            return struct.unpack("<i", data[:4])[0]
        elif cip_type_code == 0xCA:  # REAL
            return struct.unpack("<f", data[:4])[0]
        else:
            # Default to DINT
            return struct.unpack("<i", data[:4])[0] if len(data) >= 4 else 0
