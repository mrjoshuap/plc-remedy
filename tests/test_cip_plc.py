"""Unit tests for CIP-compatible mock PLC."""
import pytest
from unittest.mock import Mock, patch, MagicMock

from mock.tag_manager import TagManager, OperatingMode
from mock.cip_objects import TagObject, ConnectionManager, IdentityObject
from mock.cip_services import CIPServiceHandler, SERVICE_READ_TAG, SERVICE_WRITE_TAG


@pytest.fixture
def tag_manager():
    """Create a test tag manager."""
    return TagManager(OperatingMode.NORMAL)


@pytest.fixture
def tag_object(tag_manager):
    """Create a test tag object."""
    return TagObject(tag_manager)


@pytest.fixture
def connection_manager():
    """Create a test connection manager."""
    return ConnectionManager()


@pytest.fixture
def identity_object():
    """Create a test identity object."""
    return IdentityObject()


@pytest.fixture
def service_handler(tag_object, connection_manager, identity_object):
    """Create a test service handler."""
    return CIPServiceHandler(tag_object, connection_manager, identity_object)


def test_tag_manager_init(tag_manager):
    """Test tag manager initialization."""
    assert tag_manager.mode == OperatingMode.NORMAL
    assert len(tag_manager.tags) > 0


def test_tag_manager_get_tag_value_normal(tag_manager):
    """Test getting tag value in normal mode."""
    value = tag_manager.get_tag_value("Light_Status")
    assert isinstance(value, bool)
    assert value is True  # Nominal value


def test_tag_manager_get_tag_value_failed(tag_manager):
    """Test getting tag value in failed mode."""
    tag_manager.set_mode(OperatingMode.FAILED)
    value = tag_manager.get_tag_value("Light_Status")
    assert isinstance(value, bool)
    assert value is False  # Failure value


def test_tag_manager_set_tag_value(tag_manager):
    """Test setting tag value."""
    success = tag_manager.set_tag_value("Motor_Speed", 2000)
    assert success is True
    
    # Value should be updated (though mode transformation may still apply)
    assert tag_manager.tags["Motor_Speed"]["value"] == 2000


def test_tag_object_read_tag(tag_object):
    """Test tag object read operation."""
    success, data_type, value_bytes = tag_object.read_tag(b"Light_Status")
    assert success is True
    assert data_type == 0xC1  # BOOL type code
    assert len(value_bytes) > 0


def test_tag_object_write_tag(tag_object):
    """Test tag object write operation."""
    # Write a DINT value
    success = tag_object.write_tag(b"Motor_Speed", 0xC4, b"\x00\x00\x07\x08")  # 1800 in DINT
    assert success is True


def test_connection_manager_forward_open(connection_manager):
    """Test Forward Open operation."""
    # Simplified Forward Open request
    request_data = b"\x00" * 50  # Mock request data
    success, response, conn_o_to_t, conn_t_to_o = connection_manager.forward_open(request_data)
    
    assert success is True
    assert conn_o_to_t > 0
    assert conn_t_to_o > 0
    assert len(response) > 0


def test_identity_object_get_attribute(identity_object):
    """Test identity object attribute retrieval."""
    # Test vendor ID attribute
    attr_value = identity_object.get_attribute(1)  # ATTR_VENDOR_ID
    assert attr_value is not None
    assert len(attr_value) == 2  # UINT16


def test_service_handler_read_tag(service_handler):
    """Test service handler Read Tag."""
    success, status, response = service_handler.handle_service(
        SERVICE_READ_TAG, b"Light_Status", b""
    )
    assert success is True
    assert status == 0x00  # Success
    assert len(response) > 0


def test_service_handler_write_tag(service_handler):
    """Test service handler Write Tag."""
    # Write BOOL value
    request_data = b"\xC1\x01"  # BOOL type + True value
    success, status, response = service_handler.handle_service(
        SERVICE_WRITE_TAG, b"Light_Status", request_data
    )
    assert success is True
    assert status == 0x00  # Success


def test_tag_manager_list_tags(tag_manager):
    """Test listing tags."""
    tags = tag_manager.list_tags()
    assert len(tags) > 0
    assert "Light_Status" in tags
    assert "Motor_Speed" in tags


def test_tag_manager_statistics(tag_manager):
    """Test getting statistics."""
    # Perform some operations
    tag_manager.get_tag_value("Light_Status")
    tag_manager.set_tag_value("Motor_Speed", 1800)
    
    stats = tag_manager.get_statistics()
    assert stats["read_count"] > 0
    assert stats["write_count"] > 0
    assert stats["total_tags"] > 0
