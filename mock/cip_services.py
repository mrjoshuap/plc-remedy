"""CIP service handlers for mock PLC."""
import struct
import logging
from typing import Tuple, Optional
try:
    from mock.cip_objects import TagObject, ConnectionManager, IdentityObject
except ImportError:
    # Handle relative imports
    from cip_objects import TagObject, ConnectionManager, IdentityObject

logger = logging.getLogger(__name__)


# CIP Service Codes
SERVICE_GET_ATTRIBUTE_ALL = 0x01
SERVICE_GET_ATTRIBUTE_LIST = 0x03
SERVICE_GET_ATTRIBUTE_SINGLE = 0x03
SERVICE_SET_ATTRIBUTE_SINGLE = 0x04
SERVICE_RESET = 0x05
SERVICE_START = 0x06
SERVICE_STOP = 0x07
SERVICE_CREATE = 0x08
SERVICE_DELETE = 0x09
SERVICE_MULTIPLE_SERVICE_PACKET = 0x0A
SERVICE_APPLY_ATTRIBUTES = 0x0D
SERVICE_GET_ATTRIBUTE_SINGLE = 0x0E
SERVICE_SET_ATTRIBUTE_SINGLE = 0x10
SERVICE_FIND_NEXT = 0x11
SERVICE_RESTORE = 0x15
SERVICE_SAVE = 0x16
SERVICE_NO_OPERATION = 0x17
SERVICE_GET_MEMBER = 0x18
SERVICE_SET_MEMBER = 0x19
SERVICE_INSERT_MEMBER = 0x1A
SERVICE_REMOVE_MEMBER = 0x1B
SERVICE_GROUP_SYNC = 0x1C
SERVICE_READ_TAG = 0x4C
SERVICE_WRITE_TAG = 0x4D
SERVICE_READ_TAG_FRAGMENTED = 0x52
SERVICE_WRITE_TAG_FRAGMENTED = 0x53
SERVICE_FORWARD_OPEN = 0x54
SERVICE_FORWARD_CLOSE = 0x4E
SERVICE_GET_CONNECTION_DATA = 0x56
SERVICE_SEARCH_CONNECTION_DATA = 0x57
SERVICE_FIND_NEXT_CONNECTION = 0x5A
SERVICE_READ_MODIFY_WRITE_TAG = 0x4E


# CIP Error Codes
ERROR_SUCCESS = 0x00
ERROR_CONNECTION_FAILURE = 0x01
ERROR_RESOURCE_UNAVAILABLE = 0x02
ERROR_INVALID_PARAMETER_VALUE = 0x03
ERROR_PATH_SEGMENT_ERROR = 0x04
ERROR_PATH_DESTINATION_UNKNOWN = 0x05
ERROR_PARTIAL_TRANSFER = 0x06
ERROR_CONNECTION_LOST = 0x07
ERROR_SERVICE_NOT_SUPPORTED = 0x08
ERROR_INVALID_ATTRIBUTE_VALUE = 0x09
ERROR_ATTRIBUTE_LIST_ERROR = 0x0A
ERROR_ALREADY_IN_REQUESTED_MODE = 0x0B
ERROR_OBJECT_STATE_CONFLICT = 0x0C
ERROR_OBJECT_ALREADY_EXISTS = 0x0D
ERROR_ATTRIBUTE_NOT_SETTABLE = 0x0E
ERROR_PRIVILEGE_VIOLATION = 0x0F
ERROR_DEVICE_STATE_CONFLICT = 0x10
ERROR_REPLY_DATA_TOO_LARGE = 0x11
ERROR_FRAGMENTATION_PRIMITIVE = 0x12
ERROR_NOT_ENOUGH_DATA = 0x13
ERROR_ATTRIBUTE_NOT_SUPPORTED = 0x14
ERROR_TOO_MUCH_DATA = 0x15
ERROR_OBJECT_DOES_NOT_EXIST = 0x16
ERROR_VENDOR_SPECIFIC = 0x80


class CIPServiceHandler:
    """Handler for CIP service requests."""
    
    def __init__(self, tag_object: TagObject, connection_manager: ConnectionManager, 
                 identity_object: IdentityObject):
        """Initialize service handler.
        
        Args:
            tag_object: TagObject instance
            connection_manager: ConnectionManager instance
            identity_object: IdentityObject instance
        """
        self.tag_object = tag_object
        self.connection_manager = connection_manager
        self.identity_object = identity_object
    
    def handle_service(self, service_code: int, request_path: bytes, 
                      request_data: bytes) -> Tuple[bool, int, bytes]:
        """Handle CIP service request.
        
        Args:
            service_code: CIP service code
            request_path: Request path (class/instance/attribute)
            request_data: Service-specific request data
            
        Returns:
            Tuple of (success: bool, status_code: int, response_data: bytes)
        """
        try:
            if service_code == SERVICE_READ_TAG:
                return self.handle_read_tag(request_path, request_data)
            elif service_code == SERVICE_WRITE_TAG:
                return self.handle_write_tag(request_path, request_data)
            elif service_code == SERVICE_FORWARD_OPEN:
                return self.handle_forward_open(request_path, request_data)
            elif service_code == SERVICE_FORWARD_CLOSE:
                return self.handle_forward_close(request_path, request_data)
            elif service_code == SERVICE_GET_ATTRIBUTE_SINGLE:
                return self.handle_get_attribute_single(request_path, request_data)
            elif service_code == SERVICE_MULTIPLE_SERVICE_PACKET:
                return self.handle_multiple_service_packet(request_data)
            else:
                logger.warning(f"Unsupported service code: 0x{service_code:02X}")
                return (False, ERROR_SERVICE_NOT_SUPPORTED, b"")
        except Exception as e:
            logger.error(f"Service handler error: {e}", exc_info=True)
            return (False, ERROR_CONNECTION_FAILURE, b"")
    
    def handle_read_tag(self, tag_path: bytes, request_data: bytes) -> Tuple[bool, int, bytes]:
        """Handle Read Tag service (0x4C).
        
        Args:
            tag_path: Tag path
            request_data: Request data (usually empty for Read Tag)
            
        Returns:
            Tuple of (success, status_code, response_data)
        """
        success, data_type, value_bytes = self.tag_object.read_tag(tag_path)
        
        if success:
            # Response: Status (1 byte) + Data Type (1 byte) + Data
            response = struct.pack("<B", ERROR_SUCCESS)  # Status
            response += struct.pack("<B", data_type)  # Data type
            response += value_bytes  # Value
            return (True, ERROR_SUCCESS, response)
        else:
            return (False, ERROR_OBJECT_DOES_NOT_EXIST, b"")
    
    def handle_write_tag(self, tag_path: bytes, request_data: bytes) -> Tuple[bool, int, bytes]:
        """Handle Write Tag service (0x4D).
        
        Args:
            tag_path: Tag path
            request_data: Request data (data type + value)
            
        Returns:
            Tuple of (success, status_code, response_data)
        """
        if len(request_data) < 2:
            return (False, ERROR_NOT_ENOUGH_DATA, b"")
        
        data_type = request_data[0]
        value_data = request_data[1:]
        
        success = self.tag_object.write_tag(tag_path, data_type, value_data)
        
        if success:
            # Response: Status (1 byte)
            response = struct.pack("<B", ERROR_SUCCESS)
            return (True, ERROR_SUCCESS, response)
        else:
            return (False, ERROR_OBJECT_DOES_NOT_EXIST, b"")
    
    def handle_forward_open(self, request_path: bytes, request_data: bytes) -> Tuple[bool, int, bytes]:
        """Handle Forward Open service (0x54).
        
        Args:
            request_path: Connection Manager path
            request_data: Forward Open request data
            
        Returns:
            Tuple of (success, status_code, response_data)
        """
        success, response_data, conn_id_o_to_t, conn_id_t_to_o = \
            self.connection_manager.forward_open(request_data)
        
        if success:
            return (True, ERROR_SUCCESS, response_data)
        else:
            return (False, ERROR_CONNECTION_FAILURE, response_data)
    
    def handle_forward_close(self, request_path: bytes, request_data: bytes) -> Tuple[bool, int, bytes]:
        """Handle Forward Close service (0x4E).
        
        Args:
            request_path: Connection Manager path
            request_data: Forward Close request data
            
        Returns:
            Tuple of (success, status_code, response_data)
        """
        # Parse connection ID from request (simplified)
        if len(request_data) >= 4:
            connection_id = struct.unpack("<I", request_data[:4])[0]
            success = self.connection_manager.forward_close(connection_id)
            
            if success:
                response = struct.pack("<H", ERROR_SUCCESS)
                return (True, ERROR_SUCCESS, response)
        
        return (False, ERROR_CONNECTION_FAILURE, b"")
    
    def handle_get_attribute_single(self, request_path: bytes, 
                                    request_data: bytes) -> Tuple[bool, int, bytes]:
        """Handle Get Attribute Single service (0x03).
        
        Args:
            request_path: Object path (class/instance)
            request_data: Attribute ID (2 bytes)
            
        Returns:
            Tuple of (success, status_code, response_data)
        """
        # Parse path to determine object
        if len(request_path) < 2:
            return (False, ERROR_PATH_SEGMENT_ERROR, b"")
        
        class_id = request_path[0]
        instance_id = request_path[1] if len(request_path) > 1 else 1
        
        if len(request_data) < 2:
            return (False, ERROR_NOT_ENOUGH_DATA, b"")
        
        attribute_id = struct.unpack("<H", request_data[:2])[0]
        
        # Handle Identity Object
        if class_id == 0x01 and instance_id == 0x01:
            attr_value = self.identity_object.get_attribute(attribute_id)
            if attr_value:
                # Response: Status (1 byte) + Attribute Data
                response = struct.pack("<B", ERROR_SUCCESS) + attr_value
                return (True, ERROR_SUCCESS, response)
            else:
                return (False, ERROR_ATTRIBUTE_NOT_SUPPORTED, b"")
        
        return (False, ERROR_OBJECT_DOES_NOT_EXIST, b"")
    
    def handle_multiple_service_packet(self, request_data: bytes) -> Tuple[bool, int, bytes]:
        """Handle Multiple Service Packet (0x0A).
        
        Args:
            request_data: Multiple service packet data
            
        Returns:
            Tuple of (success, status_code, response_data)
        """
        # Parse multiple service packet
        # Format: Count (1 byte) + [Offset (2 bytes) + Service Code (1 byte) + Path + Data]...
        if len(request_data) < 1:
            return (False, ERROR_NOT_ENOUGH_DATA, b"")
        
        count = request_data[0]
        offset = 1
        responses = []
        
        for i in range(count):
            if offset + 2 > len(request_data):
                break
            
            # Read offset to next service
            next_offset = struct.unpack("<H", request_data[offset:offset+2])[0]
            offset += 2
            
            if offset >= len(request_data):
                break
            
            # Read service code
            service_code = request_data[offset]
            offset += 1
            
            # Parse path (simplified)
            # In real implementation, would parse full CIP path
            path_length = 2  # Assume class + instance
            if offset + path_length > len(request_data):
                break
            
            request_path = request_data[offset:offset+path_length]
            offset += path_length
            
            # Remaining data is service-specific
            service_data = request_data[offset:offset+next_offset-3-path_length] if next_offset > 0 else b""
            
            # Handle service
            success, status, response_data = self.handle_service(
                service_code, request_path, service_data
            )
            
            # Build response for this service
            service_response = struct.pack("<B", status) + response_data
            responses.append(service_response)
            
            if next_offset > 0:
                offset += next_offset - 3 - path_length
            else:
                break
        
        # Build multiple service response
        response = struct.pack("<B", count)  # Count
        for resp in responses:
            response += struct.pack("<H", len(resp) + 2)  # Offset
            response += resp
        
        return (True, ERROR_SUCCESS, response)
