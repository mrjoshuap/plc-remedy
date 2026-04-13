"""Test script to verify CIP PLC connection."""
import logging
import sys
import time

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

try:
    from pycomm3 import LogixDriver
    PYCOMM3_AVAILABLE = True
except ImportError:
    PYCOMM3_AVAILABLE = False
    logger.error("pycomm3 not installed")
    sys.exit(1)

def test_connection(ip="127.0.0.1", timeout=5.0):
    """Test connection to CIP PLC.

    Args:
        ip: PLC IP address
        timeout: Connection timeout
    """
    logger.info(f"Testing connection to {ip}...")
    logger.info(f"Timeout: {timeout} seconds")

    try:
        driver = LogixDriver(ip, timeout=timeout)
        logger.info("Attempting to open connection...")
        driver.open()

        if driver.connected:
            logger.info("Connection successful!")

            # Try to read a tag
            logger.info("Testing tag read...")
            try:
                result = driver.read("Light_Status")
                if result.error:
                    logger.error(f"Tag read error: {result.error}")
                else:
                    logger.info(f"Tag read successful: Light_Status = {result.value}")
            except Exception as e:
                logger.error(f"Tag read failed: {e}")

            driver.close()
            logger.info("Connection test completed successfully!")
            return True
        else:
            logger.error("Connection failed: driver reports not connected")
            return False

    except Exception as e:
        logger.error(f"Connection failed: {e}")
        logger.info("Troubleshooting:")
        logger.info("1. Is the mock PLC running?")
        logger.info("   python mock/cip_plc.py --ip 127.0.0.1 --port 44818")
        logger.info("2. Is port 44818 listening?")
        logger.info("   netstat -an | grep 44818")
        logger.info("3. Check firewall settings")
        return False

if __name__ == "__main__":
    ip = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    success = test_connection(ip)
    sys.exit(0 if success else 1)
