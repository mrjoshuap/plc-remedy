# Troubleshooting Guide

## Common Issues and Solutions

### Issue: "A session must be registered before a Forward Open"

**Symptoms:**
- PLC client fails to connect
- Error message: "A session must be registered before a Forward Open"
- Connection timeout errors

**Causes:**
1. Mock PLC server is not running
2. Mock PLC server is not listening on the correct port
3. cpppo server is not starting correctly
4. Network/firewall blocking port 44818

**Solutions:**

1. **Verify Mock PLC is Running:**
```bash
# Check if process is running
ps aux | grep cip_plc

# Check if port is listening
netstat -an | grep 44818
# or
lsof -i :44818
```

2. **Start Mock PLC Correctly:**
```bash
# Make sure all dependencies are installed
pip install -r requirements.txt

# Start the CIP PLC
python mock/cip_plc.py --ip 127.0.0.1 --port 44818 --mode normal

# You should see:
# "CIP PLC server starting with cpppo on 127.0.0.1:44818"
# "Tags: ['Light_Status', 'Motor_Speed', ...]"
```

3. **Check Configuration:**
```yaml
# config/config.yaml
plc:
  ip_address: "127.0.0.1"  # Must match mock PLC IP
  slot: 0
  timeout: 5.0
```

4. **Test Connection Manually:**
```python
from pycomm3 import LogixDriver

driver = LogixDriver("127.0.0.1")
try:
    driver.open()
    print(f"Connected: {driver.connected}")
    if driver.connected:
        result = driver.read("Light_Status")
        print(f"Read successful: {result.value}")
    driver.close()
except Exception as e:
    print(f"Connection failed: {e}")
```

### Issue: "TemplateNotFound: dashboard.html"

**Solution:** Already fixed - template folder is configured in `run.py`

### Issue: Flask Reloader Disconnecting PLC

**Solution:** Already fixed - reloader is disabled in `run.py`

### Issue: Mock PLC Not Responding

**Checklist:**
1. Is cpppo installed? `pip list | grep cpppo`
2. Is the mock PLC process running?
3. Are there any error messages in the mock PLC logs?
4. Is port 44818 available? (not used by another process)
5. Try using `127.0.0.1` instead of `0.0.0.0` for binding

### Issue: Tag Not Found Errors

**Causes:**
- Tag name mismatch (case-sensitive)
- Tag not defined in TagManager

**Solution:**
- Verify tag names match exactly between config.yaml and TagManager.DEFAULT_TAGS
- Check tag names are case-sensitive

### Issue: cpppo Import Errors

**Solution:**
Install all dependencies from requirements.txt:
```bash
pip install -r requirements.txt
```

If using conda:
```bash
# Create/activate conda environment first
conda create -n plc-remedy python=3.10
conda activate plc-remedy

# Install dependencies
pip install -r requirements.txt
```

### Issue: Application Crashes on Startup

**Check:**
1. All dependencies installed: `pip install -r requirements.txt`
2. Configuration file exists: `config/config.yaml`
3. Configuration is valid YAML
4. Check application logs for specific error messages

### Issue: Dashboard Not Updating

**Check:**
1. WebSocket connection in browser console
2. Socket.IO server is running (check logs)
3. Monitor service is running (check logs)
4. Browser compatibility (modern browser required)

### Issue: Slow Response Times

**Possible Causes:**
- Network latency
- High polling frequency
- Too many tags being read
- System resource constraints

**Solutions:**
- Increase `poll_interval_ms` in config
- Reduce number of monitored tags
- Check system resources (CPU, memory)

## Diagnostic Commands

### Check Mock PLC Status
```bash
# Check if running
ps aux | grep cip_plc

# Check port
netstat -an | grep 44818

# Test connection
telnet 127.0.0.1 44818
```

### Check Application Status
```bash
# Check if running
ps aux | grep run.py

# Check port
netstat -an | grep 15000

# Test API
curl http://localhost:15000/api/v1/health
```

### Verify Configuration
```bash
# Check config file exists
ls -la config/config.yaml

# Validate YAML syntax
python -c "import yaml; yaml.safe_load(open('config/config.yaml'))"
```

## Getting Help

1. Check application logs for detailed error messages
2. Review mock PLC logs for connection attempts
3. Test with a real PLC if available (to isolate mock PLC issues)
4. Check pycomm3 documentation for client-side issues
5. Review cpppo documentation for server-side issues

## Log Levels

Increase logging verbosity for debugging by configuring the log level in `config/config.yaml`:

```yaml
logging:
  level: DEBUG  # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL
```

**Valid log levels:**
- `DEBUG`: Most verbose, shows all diagnostic information
- `INFO`: General informational messages (default)
- `WARNING`: Warning messages only
- `ERROR`: Error messages only
- `CRITICAL`: Critical errors only

The log level is case-insensitive. After changing the log level in config.yaml, restart the application for the change to take effect.
