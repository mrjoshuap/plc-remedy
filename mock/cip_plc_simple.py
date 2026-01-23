"""Simplified CIP PLC using cpppo - direct integration."""
import argparse
import logging
import sys
from cpppo.server.enip import device
from cpppo.server.enip import main as enip_main

from mock.tag_manager import TagManager, OperatingMode

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ModeAwareAttribute(device.Attribute):
    """cpppo Attribute that applies operating mode transformations."""

    def __init__(self, tag_manager, tag_name, parser, *args, **kwargs):
        """Initialize mode-aware attribute.

        Args:
            tag_manager: TagManager instance
            tag_name: Name of the tag
            parser: cpppo parser (BOOL, DINT, etc.)
        """
        super().__init__(parser, *args, **kwargs)
        self.tag_manager = tag_manager
        self.tag_name = tag_name
        self.name = tag_name  # Set name for cpppo

    def __getitem__(self, key):
        """Get tag value with mode transformation."""
        try:
            value = self.tag_manager.get_tag_value(self.tag_name)
            logger.debug(f"Read {self.tag_name}: {value}")
            return value
        except (KeyError, Exception) as e:
            logger.warning(f"Error reading {self.tag_name}: {e}")
            return 0

    def __setitem__(self, key, value):
        """Set tag value."""
        try:
            self.tag_manager.set_tag_value(self.tag_name, value)
            logger.debug(f"Write {self.tag_name}: {value}")
        except Exception as e:
            logger.error(f"Error writing {self.tag_name}: {e}")


def create_cip_plc(ip="127.0.0.1", port=44818, mode=OperatingMode.NORMAL):
    """Create and configure CIP PLC with cpppo.

    Args:
        ip: IP address to bind to
        port: Port to listen on
        mode: Operating mode

    Returns:
        Tuple of (tag_manager, tag_defs_dict)
    """
    # Initialize tag manager
    tag_manager = TagManager(mode)
    tag_manager.set_mode(mode)

    # Build tag definitions for cpppo
    # Format: name -> Attribute instance
    from cpppo.server.enip import BOOL, DINT, REAL

    tag_defs = {}
    for tag_name in tag_manager.list_tags():
        tag_info = tag_manager.get_tag_info(tag_name)
        tag_type = tag_info["type"]

        # Create appropriate parser
        if tag_type == "BOOL":
            parser = BOOL
        elif tag_type in ["INT", "DINT"]:
            parser = DINT
        elif tag_type == "REAL":
            parser = REAL
        else:
            parser = DINT

        # Create mode-aware attribute
        tag_defs[tag_name] = ModeAwareAttribute(
            tag_manager, tag_name, parser
        )

    return tag_manager, tag_defs


def main():
    """Main entry point for simplified CIP PLC."""
    parser = argparse.ArgumentParser(description="CIP-Compatible Mock PLC (Simplified)")
    parser.add_argument("--ip", default="127.0.0.1", help="IP address to bind to")
    parser.add_argument("--port", type=int, default=44818, help="Port to listen on")
    parser.add_argument("--mode", choices=["normal", "degraded", "failed", "unresponsive"],
                     default="normal", help="Operating mode")

    args = parser.parse_args()

    mode = OperatingMode(args.mode)

    # Create tag manager and definitions
    tag_manager, tag_defs = create_cip_plc(args.ip, args.port, mode)

    # Build tag definitions in format cpppo expects: name -> (type_string, count)
    cpppo_tag_defs = {}
    for tag_name, attr in tag_defs.items():
        tag_info = tag_manager.get_tag_info(tag_name)
        tag_type = tag_info["type"]

        if tag_type == "BOOL":
            cpppo_type = "BOOL"
        elif tag_type in ["INT", "DINT"]:
            cpppo_type = "DINT"
        elif tag_type == "REAL":
            cpppo_type = "REAL"
        else:
            cpppo_type = "DINT"

        cpppo_tag_defs[tag_name] = (cpppo_type, 1)

    # Build address
    address = f"{args.ip}:{args.port}"

    logger.info(f"Starting CIP PLC on {address} in {mode.value} mode")
    logger.info(f"Available tags: {', '.join(tag_manager.list_tags())}")

    # Create a custom attribute factory that uses our ModeAwareAttribute
    def attribute_factory(name, parser, *args, **kwargs):
        """Factory function to create ModeAwareAttribute instances."""
        if name in tag_defs:
            return tag_defs[name]
        # Fallback for unknown tags
        return ModeAwareAttribute(tag_manager, name, parser, *args, **kwargs)

    # Run cpppo server
    # Note: enip_main modifies sys.argv, so we need to handle that
    original_argv = sys.argv
    try:
        sys.argv = [
            'cip_plc_simple.py',
            '--address', address,
            '--print',  # Print I/O for debugging
        ]

        enip_main(
            attribute_class=attribute_factory,
            tags=cpppo_tag_defs,
            args=sys.argv[1:]
        )
    finally:
        sys.argv = original_argv


if __name__ == "__main__":
    main()
