# Mock PLC Simulators

This directory contains mock PLC simulators for testing the PLC Self-Healing Middleware without requiring a physical PLC.

## CIP-Compatible Mock PLC (Recommended)

**File:** `cip_plc.py`

A full CIP protocol-compatible PLC simulator that works seamlessly with `pycomm3`.

### Features

- Full CIP protocol implementation via `cpppo` library
- Compatible with pycomm3 LogixDriver
- Session registration (RegisterSession/UnRegisterSession)
- Forward Open support for connection establishment
- Tag Read/Write services (0x4C, 0x4D)
- Device Identity Object
- Operating mode support (normal, degraded, failed, unresponsive)

### Usage

```bash
python mock/cip_plc.py --ip 127.0.0.1 --port 44818 --mode normal
```

### Requirements

All dependencies are installed via requirements.txt:
```bash
pip install -r requirements.txt
```

### Testing with pycomm3

```python
from pycomm3 import LogixDriver

driver = LogixDriver("127.0.0.1")
driver.open()

if driver.connected:
    result = driver.read("Light_Status")
    print(f"Light_Status: {result.value}")

driver.close()
```

## Architecture

```
mock/
├── cip_plc.py          # Main CIP-compatible PLC simulator
├── tag_manager.py      # Tag storage and mode transformations
├── cip_objects.py      # CIP object definitions
└── cip_services.py     # CIP service handlers
```

## Operating Modes

The CIP-compatible mock PLC supports the following operating modes:

- **normal**: Returns nominal values with small random variance
- **degraded**: Gradually drifts toward failure thresholds over time
- **failed**: Returns failure condition values immediately
- **unresponsive**: Stops responding to simulate network issues

## Tag Definitions

Default tags match the configuration in `config/config.yaml`:

- `Light_Status` (BOOL): Light on/off status
- `Motor_Speed` (DINT): Motor RPM (nominal: 1750)
- `Motor_Direction` (DINT): Motor direction (0=stopped, 1=forward, 2=reverse)
- `Motor_Run` (BOOL): Motor run command

## Documentation

- [MOCK_PLC_LIMITATIONS.md](../MOCK_PLC_LIMITATIONS.md) - Mock PLC limitations and Micro800 simulation requirements

## Troubleshooting

### cpppo Import Error

If you see `ImportError: cpppo is required`:

```bash
# Install all dependencies from requirements.txt
pip install -r requirements.txt
```

### Connection Issues

1. Verify the PLC is running: `netstat -an | grep 44818`
2. Check firewall settings
3. Ensure IP address matches (127.0.0.1 for localhost)
4. Review application logs

### Tag Not Found

- Verify tag names match exactly (case-sensitive)
- Check tag definitions in TagManager.DEFAULT_TAGS
- Review logs for detailed error messages
