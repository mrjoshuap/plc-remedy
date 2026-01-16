# Testing Guide

This guide explains how to test the PLC Self-Healing Middleware using all mock components.

## Quick Test Setup

1. **Use the testing configuration:**
```bash
cp config/config.yaml.test config/config.yaml
```

2. **Start the CIP-compatible mock PLC:**
```bash
# Terminal 1: Start CIP PLC in normal mode
python mock/cip_plc.py --ip 127.0.0.1 --port 44818 --mode normal
```

**Note:** All dependencies including `cpppo` are installed via requirements.txt:
```bash
pip install -r requirements.txt
```

3. **Start the mock AAP server (optional):**
```bash
# Terminal 2: Start mock AAP (if you want to test AAP integration)
python mock/mock_aap.py
```

4. **Start the main application:**
```bash
# Terminal 3: Start the middleware
python run.py
```

5. **Open the dashboard:**
   - Navigate to http://localhost:15000
   - You should see real-time updates from the mock PLC

## Testing Scenarios

### Scenario 1: Normal Operation

1. Start CIP mock PLC in normal mode:
```bash
python mock/cip_plc.py --ip 127.0.0.1 --port 44818 --mode normal
```

2. Start the application
3. Verify:
   - Dashboard shows "Connected" status
   - Tag values are within normal ranges
   - No threshold violations
   - Charts show stable values

### Scenario 2: Threshold Violation Detection

1. Start CIP mock PLC in degraded mode:
```bash
python mock/cip_plc.py --mode degraded
```

2. Watch the dashboard:
   - Values should gradually drift toward failure thresholds
   - Violations should appear in the Alerts Panel
   - Event log should show threshold_violation events

3. Test remediation:
   - Click "Emergency Reset" button
   - Verify AAP job is triggered (check AAP Job Status table)
   - In real scenario, this would reset PLC values

### Scenario 3: Connection Loss

1. Start CIP mock PLC in unresponsive mode:
```bash
python mock/cip_plc.py --mode unresponsive
```

2. Watch the dashboard:
   - Connection status should change to "Disconnected"
   - Event log should show "connection_lost" event
   - Tag values should show errors

3. Restore connection:
   - Stop the unresponsive mock PLC
   - Start in normal mode
   - Connection should restore automatically

### Scenario 4: Chaos Engineering

1. Start CIP mock PLC in normal mode:
```bash
python mock/cip_plc.py --ip 127.0.0.1 --port 44818 --mode normal
```

2. In the dashboard:
   - Enable "Chaos Injection" toggle
   - Set injection rate (e.g., 10-50%)
   - Watch for injected failures in event log

3. Understand failure durations:
   - **Value anomalies**: Persist for 1-180 seconds (random duration)
   - **Network timeouts**: Use configured duration from config.yaml
   - **Connection loss**: Use configured duration from config.yaml

4. Test specific injections:
   - Click "Inject Timeout" button
   - Click "Inject Connection Loss" button
   - Verify failures appear in event log
   - Observe that value anomalies persist for random durations (1-180 seconds)

5. Test remediation during active failures:
   - Trigger remediation actions while failures are active
   - Verify system handles failures gracefully

### Scenario 5: Failed State

1. Start CIP mock PLC in failed mode:
```bash
python mock/cip_plc.py --mode failed
```

2. Verify:
   - All tags show failure condition values
   - Multiple threshold violations appear
   - Dashboard shows critical alerts

3. Test emergency stop:
   - Click "Emergency Stop" button
   - Verify remediation job is triggered

## API Testing

### Test Health Endpoint
```bash
curl http://localhost:15000/api/v1/health
```

### Test Status Endpoint
```bash
curl http://localhost:15000/api/v1/status | jq
```

### Test Tag Reading
```bash
curl http://localhost:15000/api/v1/tags | jq
```

### Test Remediation
```bash
# Trigger emergency reset
curl -X POST http://localhost:15000/api/v1/remediate/reset | jq

# Check status
curl http://localhost:15000/api/v1/remediate/status | jq
```

### Test Chaos Engineering
```bash
# Get chaos status
curl http://localhost:15000/api/v1/chaos/status | jq

# Enable chaos
curl -X POST http://localhost:15000/api/v1/chaos/enable | jq

# Inject connection loss
curl -X POST http://localhost:15000/api/v1/chaos/inject \
  -H "Content-Type: application/json" \
  -d '{"failure_type": "connection_loss", "duration_seconds": 10}' | jq
```

## Running Unit Tests

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_plc_client.py

# Run with verbose output
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html
```

## Mock PLC Notes

### CIP-Compatible Mock PLC

The `cip_plc.py` provides full CIP protocol support and is compatible with pycomm3. All dependencies including `cpppo` are installed via `requirements.txt`.

**Important:** Due to limitations in the cpppo library and pycomm3's protocol handling, the mock PLC must simulate a Micro800 PLC. This is because pycomm3 only disables Multiple Service Packets (MSP) for Micro800 devices, which is necessary since the mock PLC cannot properly handle MSP requests. The application automatically configures pycomm3 to treat the mock PLC as a Micro800 device when in mock mode.

For best results:
1. **Use a real PLC** for production testing
2. **Use commercial PLC simulators** for more accurate testing
3. **Test with mock PLC** for basic functionality validation

If you encounter connection issues with the mock PLC:
- Verify the mock PLC is running: `netstat -an | grep 44818`
- Check firewall settings
- Try connecting with a simple TCP client first
- Consider using a real PLC or commercial simulator

## Troubleshooting Tests

### Mock PLC Not Responding
- Check if port 44818 is available: `lsof -i :44818`
- Verify mock PLC is running: Check terminal output
- Try different IP: Use `0.0.0.0` instead of `127.0.0.1`

### Application Can't Connect
- Verify config.yaml has correct IP: `127.0.0.1` for localhost
- Check timeout settings (increase if needed)
- Review application logs for error messages

### Dashboard Not Updating
- Check browser console for WebSocket errors
- Verify Socket.IO connection in browser Network tab
- Restart the application

### AAP Jobs Not Triggering
- Verify `mock_mode: true` in config.yaml
- Check AAP client logs
- Test AAP endpoint directly: `curl http://localhost:8080/api/v2/job_templates/42/launch/`

## Test Checklist

- [ ] Mock PLC starts successfully
- [ ] Application connects to mock PLC
- [ ] Dashboard displays tag values
- [ ] Real-time updates work (Socket.IO)
- [ ] Threshold violations are detected
- [ ] Remediation buttons trigger AAP jobs
- [ ] Chaos injection works
- [ ] API endpoints return correct responses
- [ ] Event log shows all events
- [ ] Charts update with new data points

## Next Steps

After testing with mocks:
1. Test with a real PLC (update config.yaml with real IP)
2. Test with real AAP (set `mock_mode: false` and provide real token)
3. Test in containerized environment
4. Test with multiple PLCs (requires code extension)
