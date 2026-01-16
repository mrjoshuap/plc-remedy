"""Mock PLC and AAP simulators."""
from mock.tag_manager import TagManager, OperatingMode

try:
    from mock.cip_plc import CIPPLC
    __all__ = ['TagManager', 'OperatingMode', 'CIPPLC']
except ImportError:
    __all__ = ['TagManager', 'OperatingMode']
