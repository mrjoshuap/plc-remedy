"""Test script to verify CIP PLC connection."""
import sys
import time

try:
    from pycomm3 import LogixDriver
    PYCOMM3_AVAILABLE = True
except ImportError:
    PYCOMM3_AVAILABLE = False
    print("ERROR: pycomm3 not installed")
    sys.exit(1)

def test_connection(ip="127.0.0.1", timeout=5.0):
    """Test connection to CIP PLC.

    Args:
        ip: PLC IP address
        timeout: Connection timeout
    """
    print(f"Testing connection to {ip}...")
    print(f"Timeout: {timeout} seconds")
    print()

    try:
        driver = LogixDriver(ip, timeout=timeout)
        print("Attempting to open connection...")
        driver.open()

        if driver.connected:
            print("✓ Connection successful!")
            print()

            # Try to read a tag
            print("Testing tag read...")
            try:
                result = driver.read("Light_Status")
                if result.error:
                    print(f"✗ Tag read error: {result.error}")
                else:
                    print(f"✓ Tag read successful: Light_Status = {result.value}")
            except Exception as e:
                print(f"✗ Tag read failed: {e}")

            driver.close()
            print()
            print("Connection test completed successfully!")
            return True
        else:
            print("✗ Connection failed: driver reports not connected")
            return False

    except Exception as e:
        print(f"✗ Connection failed: {e}")
        print()
        print("Troubleshooting:")
        print("1. Is the mock PLC running?")
        print("   python mock/cip_plc.py --ip 127.0.0.1 --port 44818")
        print()
        print("2. Is port 44818 listening?")
        print("   netstat -an | grep 44818")
        print()
        print("3. Check firewall settings")
        print()
        return False

if __name__ == "__main__":
    ip = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    success = test_connection(ip)
    sys.exit(0 if success else 1)
