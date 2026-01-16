# Quick Start Guide

## Prerequisites Check

- [ ] Python 3.10+ installed
- [ ] Network access to PLC (or use mock PLC)
- [ ] Configuration file created
- [ ] tmux installed (for testing with wrapper script - optional but recommended)

## 5-Minute Setup

1. **Set up Python environment (Recommended: Conda):**

**Option A: Using Conda (Recommended)**
```bash
# Create conda environment
conda create -n plc-remedy python=3.10
conda activate plc-remedy
```

**Option B: Using Virtual Environment (Alternative)**
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```

3. **Install tmux (for testing with wrapper script):**
```bash
# macOS
brew install tmux

# Linux
sudo apt-get install tmux  # or use your distribution's package manager
```

4. **Create configuration:**
```bash
cp config/config.yaml.example config/config.yaml
# Edit config/config.yaml with your settings
```

5. **Set environment variables (if using real AAP):**
```bash
export AAP_TOKEN="your-token-here"
```

6. **Start the application:**

**Option A: Using the tmux wrapper script (Recommended for testing)**
```bash
./run_tests.sh
```

This starts all components (mock PLC, mock AAP, and main app) in separate tmux panes with all logs visible. To stop, press `Ctrl+C` or close the terminal - all components will stop automatically.

**Option B: Manual startup (Alternative)**
```bash
# Terminal 1: Start mock PLC
python mock/cip_plc.py --ip 127.0.0.1 --port 44818 --mode normal &

# Terminal 2: Start mock AAP (optional)
python mock/mock_aap.py &

# Terminal 3: Run the application
python run.py
```

7. **Open dashboard:**
   - Navigate to http://localhost:15000
   - You should see the dashboard with real-time updates

## Testing the System

### Test Threshold Detection

1. Start mock PLC in degraded mode:
```bash
python mock/cip_plc.py --ip 127.0.0.1 --port 44818 --mode degraded
```

2. Watch the dashboard for threshold violations

3. Trigger remediation:
   - Click "Emergency Reset" button in dashboard
   - Or use API: `curl -X POST http://localhost:15000/api/v1/remediate/reset`

### Test Chaos Engineering

1. Enable chaos injection in dashboard
2. Set injection rate to 50%
3. Watch for injected failures in event log
   - Value anomalies persist for 1-180 seconds (random duration)
   - Network timeouts and connection loss use configured durations

## Common Issues

### "PLC connection failed"
- Check PLC IP address in config.yaml
- Verify network connectivity: `ping <plc-ip>`
- For mock PLC, ensure it's running on port 44818

### "Dashboard not updating"
- Check browser console for WebSocket errors
- Verify Socket.IO is working: check network tab for WebSocket connection
- Restart the application

### "Configuration error"
- Verify config.yaml syntax (use a YAML validator)
- Check that all required fields are present
- Ensure environment variables are set if using `${VAR}` syntax

### "tmux not found" (when using wrapper script)
- Install tmux: `brew install tmux` (macOS) or `sudo apt-get install tmux` (Linux)
- Verify installation: `tmux -V`

## Stopping the Test Environment

If using the `run_tests.sh` wrapper script:
- Press `Ctrl+C` in any tmux pane, or
- Type `exit` in any pane, or
- Close the terminal window

All processes will be automatically stopped when the tmux session ends.

If running components manually:
- Stop each component with `Ctrl+C` in its respective terminal
- Or use `pkill -f cip_plc.py`, `pkill -f mock_aap.py`, `pkill -f run.py`

## Next Steps

- Review the full [README.md](README.md) for detailed documentation
- Explore the REST API endpoints
- Customize Ansible playbooks for your environment
- Set up containerized deployment
