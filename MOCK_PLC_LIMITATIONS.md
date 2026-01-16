# Mock PLC Limitations

## Important Note

The **original** mock PLC simulator (`mock/mock_plc.py`) has been **deprecated and removed**. It used a simplified CIP protocol and was not fully compatible with `pycomm3`.

**Current Solution:** A CIP-compatible mock PLC (`mock/cip_plc.py`) is available that provides full CIP protocol support using the `cpppo` library. See [MOCK_PLC_MIGRATION.md](MOCK_PLC_MIGRATION.md) for details.

### Known Limitations of CIP-Compatible Mock PLC

The CIP-compatible mock PLC (`mock/cip_plc.py`) has the following limitations:

1. **Multiple Service Packet (MSP) Not Supported**: 
   - pycomm3's LogixDriver may use Multiple Service Packets (MSP) for some operations
   - cpppo's parser cannot properly handle MSP requests
   - **Workaround**: The mock PLC must simulate a Micro800 PLC because pycomm3 only disables MSP for Micro800 devices. The application automatically configures pycomm3 to treat the mock PLC as a Micro800 device when in mock mode, which prevents MSP usage and allows the mock PLC to work correctly.
   - **Status**: With this workaround, basic tag reading/writing works reliably

2. **Get Attributes All for Logix Object**:
   - Some "Get Attributes All" requests for the Logix object (class 0x64) may fail
   - This doesn't prevent basic tag operations from working

3. **cpppo Library Limitations**: The `cpppo` library may not support all CIP services or advanced features

Despite these limitations, the mock PLC successfully:
- ✅ Establishes CIP sessions
- ✅ Handles Forward Open/Close
- ✅ Reads and writes tags successfully
- ✅ Works with pycomm3 for basic operations

## Micro800 Simulation Requirement

Due to limitations in the cpppo library and pycomm3's protocol handling, the mock PLC must simulate a Micro800 PLC. This is because:

1. **MSP Limitation**: The cpppo library cannot properly parse Multiple Service Packets (MSP) that pycomm3 may send for certain operations
2. **Micro800 Workaround**: pycomm3 only disables MSP usage for Micro800 devices
3. **Automatic Configuration**: When the application detects mock mode, it automatically configures pycomm3's LogixDriver to treat the connection as a Micro800 device, which disables MSP and allows the mock PLC to function correctly

This workaround is transparent to the user - simply enable mock mode in the configuration, and the application handles the Micro800 simulation automatically.

## Solutions

### Option 1: Use a Real PLC (Recommended for Testing)

1. Update `config/config.yaml` with your real PLC IP address:
```yaml
plc:
  ip_address: "192.168.1.100"  # Your real PLC IP
  slot: 0
```

2. Ensure network connectivity to the PLC
3. Run the application - it will connect to the real PLC

### Option 2: Use a Commercial PLC Simulator

Commercial PLC simulators that implement full CIP protocol:
- **FactoryTalk Linx** (Rockwell Automation)
- **RSLogix Emulate** (Rockwell Automation)
- Other commercial CIP-compatible simulators

### Option 3: Test Without PLC Connection

You can test the application's other features without a PLC:

1. **Test the Dashboard:**
   - Start the app (it will fail to connect to PLC, but that's OK)
   - Access the dashboard at http://localhost:15000
   - Test API endpoints
   - Test chaos engineering features

2. **Test AAP Integration:**
   - Start mock AAP: `python mock/mock_aap.py`
   - Trigger remediation actions via API
   - Verify AAP job creation

3. **Test Threshold Logic:**
   - Use the API to simulate tag values
   - Test violation detection logic
   - Test remediation workflows

### Option 4: Enhance Mock PLC (Advanced)

To make the mock PLC work with pycomm3, you would need to:
1. Implement full CIP protocol stack
2. Handle session registration
3. Implement Forward Open/Close
4. Handle CIP read/write requests properly
5. Respond with proper CIP packet structures

This is a significant undertaking and may not be worth the effort compared to using a real PLC or commercial simulator.

## Current Workaround

The application will:
- Attempt to connect to the PLC on startup
- Log connection failures (this is expected with mock PLC)
- Continue running and allow you to test other features
- The monitor service will retry connections periodically

You can still:
- Access the dashboard
- Test API endpoints
- Test chaos engineering
- Test AAP integration (with mock AAP)
- View the application structure and UI

## Recommendation

For development and testing:
1. **Use a real PLC** if you have access to one
2. **Use a commercial simulator** if you need full CIP compatibility
3. **Test other features** without PLC connection if you only have the mock

The mock PLC is useful for:
- Understanding the application structure
- Testing non-PLC-dependent features
- Development when a real PLC isn't available
- Learning about the application's architecture

But it **cannot** be used for testing actual PLC communication with pycomm3.
