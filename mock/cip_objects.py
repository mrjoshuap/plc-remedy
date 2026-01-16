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
        try:
            # Parse Forward Open request
            # This is a simplified parser - full implementation would parse all fields
            if len(request_data) < 50:
                return (False, b"\x00", 0, 0)  # Error response
            
            # Extract connection IDs from request (simplified)
            # In real implementation, parse priority, timeout, RPI, etc.
            connection_id_o_to_t = self.next_connection_id
            connection_id_t_to_o = self.next_connection_id + 1
            self.next_connection_id += 2
            
            connection_serial = self.next_connection_serial
            self.next_connection_serial += 1
            
            # Store connection info
            self.connections[connection_id_o_to_t] = {
                "o_to_t": connection_id_o_to_t,
                "t_to_o": connection_id_t_to_o,
                "serial": connection_serial,
                "state": "established"
            }
            
            # Build Forward Open response
            # Response structure: Extended Status (2 bytes) + Connection IDs + Serial Number
            response = struct.pack("<H", 0x0000)  # Success status
            response += struct.pack("<I", connection_id_o_to_t)  # O->T Connection ID
            response += struct.pack("<I", connection_id_t_to_o)  # T->O Connection ID
            response += struct.pack("<H", connection_serial)  # Connection Serial Number
            
            logger.info(f"Forward Open successful: O->T={connection_id_o_to_t:04X}, T->O={connection_id_t_to_o:04X}")
            return (True, response, connection_id_o_to_t, connection_id_t_to_o)
            
        except Exception as e:
            logger.error(f"Forward Open error: {e}")
            return (False, struct.pack("<H", 0x0100), 0, 0)  # Error status
    
    def forward_close(self, connection_id: int) -> bool:
        """Handle Forward Close service.
        
        Args:
            connection_id: Connection ID to close
            
        Returns:
            True if successful
        """
        if connection_id in self.connections:
            del self.connections[connection_id]
            logger.info(f"Forward Close: connection {connection_id:04X} closed")
            return True
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
        try:
            # Parse tag path (simplified - assumes ASCII tag name)
            # Real implementation would parse full CIP path structure
            tag_name = tag_path.decode('ascii', errors='ignore').strip('\x00')
            
            if not tag_name or tag_name not in self.tag_manager.tags:
                logger.warning(f"Tag not found: {tag_name}")
                return (False, 0, b"")
            
            # Get tag value
            value = self.tag_manager.get_tag_value(tag_name)
            tag_info = self.tag_manager.get_tag_info(tag_name)
            tag_type = tag_info["type"]
            
            # Convert to CIP data type code and encode value
            cip_type_code, encoded_value = self._encode_value(tag_type, value)
            
            logger.debug(f"Read tag {tag_name}: {value} (type: {tag_type})")
            return (True, cip_type_code, encoded_value)
            
        except Exception as e:
            logger.error(f"Read tag error: {e}")
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
        try:
            # Parse tag path
            tag_name = tag_path.decode('ascii', errors='ignore').strip('\x00')
            
            if not tag_name or tag_name not in self.tag_manager.tags:
                logger.warning(f"Tag not found for write: {tag_name}")
                return False
            
            # Decode value
            value = self._decode_value(data_type, value_data)
            
            # Set tag value
            success = self.tag_manager.set_tag_value(tag_name, value)
            
            if success:
                logger.debug(f"Write tag {tag_name}: {value}")
            
            return success
            
        except Exception as e:
            logger.error(f"Write tag error: {e}")
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
