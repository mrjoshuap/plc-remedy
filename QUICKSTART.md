# Quick Start Guide

## Containerized Deployment (Recommended)

Containerized deployment is the **default and recommended** method for production environments. This method provides consistent, reliable deployment with all dependencies included.

### Prerequisites Check

- [ ] Podman or Docker installed
- [ ] Network access to PLC (or use mock PLC)
- [ ] Environment variables configured (see below)

### 5-Minute Containerized Setup

1. **Build the container:**
```bash
podman build -t plc-remedy:latest .
```

2. **Create environment file:**
```bash
# Copy the example environment file
cp deployment/plc-remedy.env.example plc-remedy.env

# Edit with your settings (minimum required variables)
nano plc-remedy.env
```

**Minimum required environment variables:**
```bash
# Generate a secure Flask secret key
FLASK_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# PLC configuration
PLC_IP_ADDRESS=192.168.1.100

# AAP configuration (if using real AAP, not mock)
AAP_MOCK_MODE=true  # Set to false for real AAP
AAP_TOKEN=your-token-here  # Only needed if AAP_MOCK_MODE=false
```

3. **Run the container:**
```bash
podman run -d \
  --name plc-remedy \
  -p 15000:5000 \
  -v ./config:/app/config:ro \
  --env-file=plc-remedy.env \
  plc-remedy:latest
```

4. **Access the dashboard:**
   - Navigate to http://localhost:15000
   - You should see the dashboard with real-time updates

### Key Environment Variables for Containerized Deployment

**PLC Configuration:**
```bash
PLC_IP_ADDRESS=192.168.1.100      # Your PLC IP address (required)
PLC_SLOT=0                        # PLC slot number (default: 0)
PLC_TIMEOUT=5.0                   # Connection timeout in seconds
PLC_POLL_INTERVAL_MS=1000         # Polling interval in milliseconds
PLC_MOCK_MODE=false               # Set to "true" for mock PLC
PLC_PROTOCOL_MODE=default         # "default" or "serial"
```

**AAP Configuration:**
```bash
AAP_ENABLED=true                  # Enable AAP integration
AAP_MOCK_MODE=true                # Set to "false" for real AAP
AAP_BASE_URL=https://aap.example.com  # Only needed if AAP_MOCK_MODE=false
AAP_VERIFY_SSL=true               # Verify SSL certificates
AAP_TOKEN=your-token-here         # Required if AAP_MOCK_MODE=false
AAP_JOB_TEMPLATE_EMERGENCY_STOP=42
AAP_JOB_TEMPLATE_EMERGENCY_RESET=43
AAP_JOB_TEMPLATE_EMERGENCY_RESTART=44
AAP_JOB_TEMPLATE_GATHER_METRICS=45
```

**Tag Configuration (examples):**
```bash
# Light tag
TAG_LIGHT_NAME=Light_Status
TAG_LIGHT_TYPE=bool
TAG_LIGHT_NOMINAL=true
TAG_LIGHT_FAILURE_CONDITION=equals
TAG_LIGHT_FAILURE_VALUE=false

# Motor speed tag
TAG_MOTOR_SPEED_NAME=Motor_Speed
TAG_MOTOR_SPEED_TYPE=int
TAG_MOTOR_SPEED_NOMINAL=1750
TAG_MOTOR_SPEED_FAILURE_CONDITION=outside_range
TAG_MOTOR_SPEED_FAILURE_THRESHOLD_LOW=1500
TAG_MOTOR_SPEED_FAILURE_THRESHOLD_HIGH=2000
```

For a complete list of all environment variables, see the [Environment Variables Reference](README.md#environment-variables-reference) in the main README.

### Production Deployment with Systemd

For production deployments, see the [Production Deployment with Systemd Service](README.md#production-deployment-with-systemd-service) section in the main README for step-by-step instructions on setting up automatic startup, restart on failure, and proper logging integration.

## Development/Testing Installation

The following installation method is intended for **development and testing only**. For production deployments, use the containerized deployment method above.

### Prerequisites Check

- [ ] Python 3.10+ installed
- [ ] Conda installed (recommended) or Python venv available
- [ ] Network access to PLC (or use mock PLC)
- [ ] Configuration file created
- [ ] tmux installed (for testing with wrapper script - optional but recommended)

### 5-Minute Development Setup

0. **Install Conda (if not already installed):**

If you don't have conda installed, install it using one of the methods below. For detailed instructions, see the [Installing Conda section in README.md](README.md#installing-conda).

**macOS:**
```bash
# Option 1: Using Homebrew (Recommended)
brew install miniconda
conda init "$(basename "$SHELL")"
source ~/.zshrc  # or ~/.bash_profile

# Option 2: Download and install Miniconda
curl -O https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-x86_64.sh
bash Miniconda3-latest-MacOSX-x86_64.sh
```

**Ubuntu/Debian:**
```bash
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
chmod +x Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh
source ~/.bashrc
```

**RHEL/CentOS:**
```bash
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
chmod +x Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh
source ~/.bashrc
```

**Verify installation:**
```bash
conda --version
```

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

### "conda: command not found"
- Ensure conda is installed (see step 0 above)
- Initialize conda for your shell: `conda init "$(basename "$SHELL")"`
- Reload your shell: `source ~/.zshrc` (zsh) or `source ~/.bashrc` (bash)
- Restart your terminal
- Verify: `conda --version`

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
- For production: Set up containerized deployment with systemd service
