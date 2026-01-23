# PLC Self-Healing Middleware (plc-remedy)

A Flask-based manufacturing middleware application that monitors Allen-Bradley PLCs via CIP protocol, detects anomalies based on configurable thresholds, and triggers automated remediation through Ansible Automation Platform (AAP).

This project implements the research described in SAE Paper "From Reactive to Proactive: Applying Data Analysis and Automation to Mitigate PLC Communication Disruptions" (26MFG-0011).

## Features

- **Real-time PLC Monitoring**: Continuous polling of PLC tags via CIP protocol using pycomm3
- **Threshold Detection**: Configurable failure conditions (equals, not_equals, outside_range, below, above)
- **Automated Remediation**: Integration with Ansible Automation Platform for self-healing actions
- **Web Dashboard**: Real-time dashboard with Socket.IO updates, Chart.js visualizations, and event logging
- **Chaos Engineering**: Configurable failure injection for testing and validation
- **REST API**: Comprehensive API for integration and automation
- **Containerized**: Ready for deployment with Podman/Docker

## Architecture

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   PLC       │◄───────►│  Middleware  │◄───────►│     AAP      │
│ (CIP)       │         │   (Flask)    │         │  (Ansible)   │
└─────────────┘         └──────────────┘         └─────────────┘
                              │
                              ▼
                        ┌─────────────┐
                        │  Dashboard   │
                        │  (Web UI)    │
                        └─────────────┘
```

## Prerequisites

- Python 3.10+
- Podman or Docker (for containerized deployment)
- Access to Allen-Bradley PLC (or use mock PLC simulator)
- Ansible Automation Platform (optional, mock mode available)
- tmux (for testing with the wrapper script - see Testing section)

## Installation

### Installing Conda

Conda is the recommended Python environment manager for this project. If you don't have conda installed, follow the instructions below for your platform.

#### macOS

**Option 1: Using Homebrew (Recommended)**
```bash
# Install Miniconda via Homebrew
brew install miniconda

# Initialize conda for your shell (usually zsh or bash)
conda init "$(basename "$SHELL")"

# Restart your terminal or reload shell configuration
source ~/.zshrc  # or ~/.bash_profile for bash
```

**Option 2: Using Miniconda Installer**
```bash
# Download Miniconda installer
curl -O https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-x86_64.sh

# Run installer
bash Miniconda3-latest-MacOSX-x86_64.sh

# Follow the prompts, then restart your terminal
# Initialize conda
conda init "$(basename "$SHELL")"
source ~/.zshrc  # or ~/.bash_profile
```

**Option 3: Using Anaconda Installer**
Download the Anaconda installer from [anaconda.com](https://www.anaconda.com/products/distribution) and follow the installation wizard.

**Verification:**
```bash
conda --version
# Should display: conda 23.x.x (or similar)
```

#### Ubuntu/Debian

**Using Miniconda Installer (Recommended)**
```bash
# Download Miniconda installer for Linux
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh

# Make installer executable
chmod +x Miniconda3-latest-Linux-x86_64.sh

# Run installer
bash Miniconda3-latest-Linux-x86_64.sh

# Follow the prompts (accept license, choose installation location)
# When asked, choose "yes" to initialize conda

# Reload shell configuration
source ~/.bashrc  # or ~/.zshrc if using zsh
```

**Alternative: Using Anaconda Installer**
```bash
# Download Anaconda installer
wget https://repo.anaconda.com/archive/Anaconda3-latest-Linux-x86_64.sh

# Make executable and run
chmod +x Anaconda3-latest-Linux-x86_64.sh
bash Anaconda3-latest-Linux-x86_64.sh

# Initialize conda
source ~/.bashrc
```

**Verification:**
```bash
conda --version
# Should display: conda 23.x.x (or similar)
```

**Note:** If conda is not found after installation, you may need to manually initialize it:
```bash
# For bash
echo 'eval "$(/path/to/miniconda3/bin/conda shell.bash hook)"' >> ~/.bashrc
source ~/.bashrc

# For zsh
echo 'eval "$(/path/to/miniconda3/bin/conda shell.zsh hook)"' >> ~/.zshrc
source ~/.zshrc
```

#### RHEL/CentOS

**Using Miniconda Installer (Recommended)**
```bash
# Download Miniconda installer for Linux
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh

# Make installer executable
chmod +x Miniconda3-latest-Linux-x86_64.sh

# Run installer
bash Miniconda3-latest-Linux-x86_64.sh

# Follow the prompts (accept license, choose installation location)
# When asked, choose "yes" to initialize conda

# Reload shell configuration
source ~/.bashrc  # or ~/.zshrc if using zsh
```

**Alternative: Using Anaconda Installer**
```bash
# Download Anaconda installer
wget https://repo.anaconda.com/archive/Anaconda3-latest-Linux-x86_64.sh

# Make executable and run
chmod +x Anaconda3-latest-Linux-x86_64.sh
bash Anaconda3-latest-Linux-x86_64.sh

# Initialize conda
source ~/.bashrc
```

**Verification:**
```bash
conda --version
# Should display: conda 23.x.x (or similar)
```

**Note:** If conda is not found after installation, you may need to manually initialize it:
```bash
# For bash
echo 'eval "$(/path/to/miniconda3/bin/conda shell.bash hook)"' >> ~/.bashrc
source ~/.bashrc

# For zsh
echo 'eval "$(/path/to/miniconda3/bin/conda shell.zsh hook)"' >> ~/.zshrc
source ~/.zshrc
```

#### Additional Resources

- [Conda Documentation](https://docs.conda.io/)
- [Miniconda Installation Guide](https://docs.conda.io/en/latest/miniconda.html)
- [Anaconda Installation Guide](https://docs.anaconda.com/anaconda/install/)

**Note:** If you prefer not to use conda, you can use Python's built-in `venv` module as an alternative (see Option B in the Local Development section below).

### Local Development

1. Clone the repository:
```bash
git clone https://github.com/mrjoshuap/plc-remedy.git
cd plc-remedy
```

2. **Set up Python environment (Recommended: Conda):**

**Option A: Using Conda (Recommended)**
```bash
# Create conda environment
conda create -n plc-remedy python=3.10
conda activate plc-remedy

# Install dependencies
pip install -r requirements.txt
```

**Option B: Using Virtual Environment (Alternative)**
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

4. Configure the application:
```bash
cp config/config.yaml.example config/config.yaml
# Edit config/config.yaml with your PLC and AAP settings
```

5. Set environment variables (if needed):
```bash
export AAP_TOKEN="your-aap-token"
```

6. Run the application:
```bash
python run.py
```

The dashboard will be available at http://localhost:15000

### Containerized Deployment

#### Quick Start (Manual Container)

1. Build the container:
```bash
podman build -t plc-remedy:latest .
```

2. Run the container:
```bash
podman run -d \
  --name plc-remedy \
  -p 15000:5000 \
  -v ./config:/app/config:ro \
  -e AAP_TOKEN="${AAP_TOKEN}" \
  plc-remedy:latest
```

3. Access the dashboard at http://localhost:15000

#### Podman Deployment with Systemd Service (Recommended for Production)

This section describes how to deploy the application as a systemd service using rootless Podman, which provides automatic startup, restart on failure, and proper logging integration.

##### Prerequisites

- Podman installed and configured for rootless operation
- Systemd user services enabled (default on most modern Linux distributions)
- Access to create user systemd service files

##### Step 1: Build the Container Image

```bash
# Build the container image
podman build -t plc-remedy:latest .
```

##### Step 2: Prepare Configuration Directory

Create a directory structure for your deployment:

```bash
# Create deployment directory in your home directory
mkdir -p ~/plc-remedy/config

# Copy your config.yaml to the deployment directory
cp config/config.yaml ~/plc-remedy/config/

# Or create from example
cp config/config.yaml.example ~/plc-remedy/config/config.yaml
# Edit ~/plc-remedy/config/config.yaml with your settings
```

##### Step 3: Create Environment File

```bash
# Copy the example environment file
cp deployment/plc-remedy.env.example ~/plc-remedy/plc-remedy.env

# Edit the environment file with your configuration
nano ~/plc-remedy/plc-remedy.env
```

**Important:** Set at minimum:
- `FLASK_SECRET_KEY` - Generate a secure key: `python3 -c "import secrets; print(secrets.token_hex(32))"`
- `PLC_IP_ADDRESS` - Your PLC's IP address
- `AAP_TOKEN` - If using real AAP (not mock mode)

See [Environment Variables](#environment-variables) section for all available options.

##### Step 4: Install Systemd Service

```bash
# Copy the systemd service file to user systemd directory
mkdir -p ~/.config/systemd/user
cp deployment/plc-remedy.service ~/.config/systemd/user/

# Edit the service file to match your paths (if needed)
nano ~/.config/systemd/user/plc-remedy.service
```

**Important:** Update the following paths in the service file if your deployment directory differs:
- Volume mount path: `-v /home/%u/plc-remedy/config:/app/config:ro`
- Environment file path: `--env-file=/home/%u/plc-remedy/plc-remedy.env`
- Container image name: `plc-remedy:latest` (should match your built image)

##### Step 5: Enable and Start the Service

```bash
# Reload systemd to recognize the new service
systemctl --user daemon-reload

# Enable the service to start on boot
systemctl --user enable plc-remedy.service

# Start the service
systemctl --user start plc-remedy.service

# Check service status
systemctl --user status plc-remedy.service
```

##### Step 6: Verify Deployment

```bash
# View service logs
journalctl --user -u plc-remedy.service -f

# Check if container is running
podman ps

# Test health endpoint
curl http://localhost:15000/health
```

##### Managing the Service

```bash
# Start the service
systemctl --user start plc-remedy.service

# Stop the service
systemctl --user stop plc-remedy.service

# Restart the service
systemctl --user restart plc-remedy.service

# View service status
systemctl --user status plc-remedy.service

# View recent logs
journalctl --user -u plc-remedy.service -n 50

# Follow logs in real-time
journalctl --user -u plc-remedy.service -f

# Disable automatic startup
systemctl --user disable plc-remedy.service
```

##### Enabling Lingering for User Services

If you want the service to start automatically at boot (even when not logged in), enable lingering:

```bash
# Enable lingering for your user (requires root/sudo)
sudo loginctl enable-linger $USER

# Verify lingering is enabled
loginctl show-user $USER | grep Linger
```

##### Troubleshooting

**Service fails to start:**
- Check logs: `journalctl --user -u plc-remedy.service -n 100`
- Verify container image exists: `podman images | grep plc-remedy`
- Verify paths in service file are correct
- Check environment file syntax: `podman run --env-file ~/plc-remedy/plc-remedy.env --rm plc-remedy:latest env`

**Container exits immediately:**
- Check application logs in journalctl
- Verify config.yaml is valid YAML
- Ensure required environment variables are set
- Test container manually: `podman run --rm -it plc-remedy:latest`

**Port already in use:**
- Change port mapping in service file: `-p 15001:5000` (or another available port)
- Or stop the conflicting service

**Permission denied errors:**
- Ensure config directory is readable: `chmod -R 755 ~/plc-remedy/config`
- Check Podman is configured for rootless: `podman info | grep rootless`

##### Updating the Service

When you need to update the application:

```bash
# 1. Rebuild the container image
podman build -t plc-remedy:latest .

# 2. Restart the service
systemctl --user restart plc-remedy.service

# 3. Verify it's running
systemctl --user status plc-remedy.service
```

## Configuration

Configuration is managed via `config/config.yaml`. See `config/config.yaml.example` for a complete example.

### Key Configuration Sections

#### PLC Settings
```yaml
plc:
  ip_address: "192.168.1.100"
  slot: 0
  timeout: 5.0
  poll_interval_ms: 1000
  mock_mode: false              # Set to true when using mock PLC
  protocol_mode: "default"      # Protocol mode: "default" (use pycomm3 default) or "serial" (disable MSP, use serial methods)
                                # Note: mock_mode and protocol_mode are independent - mock_mode only sets micro800 override
```

**Protocol Mode Options:**
- `"default"` (default): Uses pycomm3's default protocol logic, which may use MSP for supported PLCs. Use this for:
  - Modern ControlLogix/CompactLogix PLCs that support MSP
  - Production environments where MSP can improve performance
  - When you want pycomm3 to handle protocol decisions automatically
- `"serial"`: Forces Micro800 mode to disable MSP and uses serial methods (sequential reads). Use this for:
  - PLCs that don't support MSP
  - Compatibility with older PLCs
  - When you need to avoid MSP for compatibility reasons

**Note:** `mock_mode` and `protocol_mode` are independent settings. When `mock_mode: true`, the application sets a micro800 override to help pycomm3 bypass MSP, but `protocol_mode` can still be set to `"default"` or `"serial"` independently.

#### Tag Monitoring
```yaml
tags:
  motor_speed:
    name: "Motor_Speed"
    type: "int"
    nominal: 1750
    failure_condition: "outside_range"
    failure_threshold_low: 1500
    failure_threshold_high: 2000
```

#### AAP Integration
```yaml
aap:
  enabled: true
  mock_mode: true  # Set to false for real AAP
  base_url: "https://aap.example.com"
  token: "${AAP_TOKEN}"  # Environment variable
  job_templates:
    emergency_stop: 42
    emergency_reset: 43
```

#### Logging Configuration
```yaml
logging:
  level: INFO  # Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"  # Optional: custom log format
```

**Valid log levels:**
- `DEBUG`: Detailed diagnostic information (most verbose)
- `INFO`: General informational messages (default)
- `WARNING`: Warning messages for potential issues
- `ERROR`: Error messages for failures
- `CRITICAL`: Critical errors that may cause the application to stop

The log level is case-insensitive. If the `logging` section is omitted, the default level is `INFO`.

### Environment Variables

All configuration values can be overridden using environment variables. This is particularly useful for containerized deployments where you want to configure the application without modifying the YAML file.

**Configuration Precedence:**
1. Environment variables (highest priority)
2. YAML config file values
3. Code defaults (lowest priority)

Environment variables use the format `${VAR_NAME:-default}` in the YAML file, where `default` is the fallback value if the environment variable is not set.

#### Flask Application Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|-----------|
| `FLASK_SECRET_KEY` | Secret key for Flask session management | `plc-remedy-secret-key-change-in-production` | Yes (in production) |

#### PLC Configuration Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|-----------|
| `PLC_IP_ADDRESS` | PLC IP address | `192.168.1.100` | Yes |
| `PLC_SLOT` | PLC slot number | `0` | No |
| `PLC_TIMEOUT` | Connection timeout in seconds | `5.0` | No |
| `PLC_POLL_INTERVAL_MS` | Polling interval in milliseconds | `1000` | No |
| `PLC_MOCK_MODE` | Enable mock mode (`"true"` or `"false"`) | `false` | No |
| `PLC_PROTOCOL_MODE` | Protocol mode: `"default"` or `"serial"` | `default` | No |

#### Tag Configuration Variables

Tag-specific variables use the format `TAG_<tag_key>_<field>`. For example:
- `TAG_LIGHT_NAME` - Name of the light tag
- `TAG_LIGHT_NOMINAL` - Nominal value for light tag
- `TAG_MOTOR_SPEED_NAME` - Name of the motor speed tag
- `TAG_MOTOR_SPEED_FAILURE_THRESHOLD_LOW` - Lower threshold for motor speed

See `deployment/plc-remedy.env.example` for complete tag variable examples.

#### AAP Configuration Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|-----------|
| `AAP_ENABLED` | Enable AAP integration (`"true"` or `"false"`) | `true` | No |
| `AAP_MOCK_MODE` | Use mock AAP responses (`"true"` or `"false"`) | `true` | No |
| `AAP_BASE_URL` | AAP base URL | `https://aap.example.com` | Yes (if `AAP_MOCK_MODE=false`) |
| `AAP_VERIFY_SSL` | Verify SSL certificates (`"true"` or `"false"`) | `true` | No |
| `AAP_TOKEN` | AAP authentication token | (empty) | Yes (if `AAP_MOCK_MODE=false`) |
| `AAP_JOB_TEMPLATE_EMERGENCY_STOP` | Job template ID for emergency stop | `42` | No |
| `AAP_JOB_TEMPLATE_EMERGENCY_RESET` | Job template ID for emergency reset | `43` | No |
| `AAP_JOB_TEMPLATE_EMERGENCY_RESTART` | Job template ID for emergency restart | `44` | No |
| `AAP_JOB_TEMPLATE_GATHER_METRICS` | Job template ID for metrics gathering | `45` | No |

#### Remediation Configuration Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|-----------|
| `REMEDIATION_AUTO_REMEDIATE` | Auto-trigger remediation (`"true"` or `"false"`) | `false` | No |
| `REMEDIATION_COOLDOWN_SECONDS` | Minimum time between remediations | `30` | No |
| `REMEDIATION_MAX_RETRIES` | Maximum retry attempts | `3` | No |

#### Chaos Engineering Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|-----------|
| `CHAOS_ENABLED` | Enable chaos injection (`"true"` or `"false"`) | `false` | No |
| `CHAOS_FAILURE_INJECTION_RATE` | Probability of failure injection (0.0-1.0) | `0.05` | No |
| `CHAOS_FAILURE_TYPES` | Comma-separated list of failure types | `value_anomaly,network_timeout,connection_loss,service_crash` | No |
| `CHAOS_NETWORK_TIMEOUT_MS` | Network timeout duration in milliseconds | `5000` | No |
| `CHAOS_ANOMALY_DURATION_SECONDS` | Anomaly duration in seconds | `10` | No |

#### Dashboard Configuration Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|-----------|
| `DASHBOARD_REFRESH_INTERVAL_MS` | Dashboard refresh interval in milliseconds | `1000` | No |
| `DASHBOARD_HISTORY_RETENTION_HOURS` | Historical data retention in hours | `24` | No |
| `DASHBOARD_CHART_DATA_POINTS` | Number of chart data points | `100` | No |

#### Logging Configuration Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|-----------|
| `LOGGING_LEVEL` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | `INFO` | No |
| `LOGGING_FORMAT` | Log message format string | `%(asctime)s - %(name)s - %(levelname)s - %(message)s` | No |

**Note:** Boolean environment variables should be set as strings: `"true"` or `"false"`. The application automatically converts these to boolean values.

For a complete example environment file, see `deployment/plc-remedy.env.example`.

## Mock PLC Simulator

### CIP-Compatible Mock PLC (Recommended)

A new **CIP-compatible mock PLC** is available that works seamlessly with `pycomm3`:

```bash
python mock/cip_plc.py --ip 127.0.0.1 --port 44818 --mode normal
```

**Features:**
- Full CIP protocol support via `cpppo` library
- Compatible with pycomm3 LogixDriver
- Session registration and Forward Open support
- Tag read/write operations
- All operating modes (normal, degraded, failed, unresponsive)

**Requirements:**
All dependencies are installed via requirements.txt:
```bash
pip install -r requirements.txt
```

**Important:** Due to limitations in the cpppo library and pycomm3's protocol handling, the mock PLC cannot properly handle Multiple Service Packets (MSP). When `mock_mode: true`, the application sets a micro800 override to help pycomm3 bypass MSP internally. However, `mock_mode` and `protocol_mode` are independent - you can still set `protocol_mode: "default"` or `"serial"` as needed.

For production PLCs, you can set `protocol_mode: "default"` to use pycomm3's default protocol logic, which allows MSP for supported PLCs and can improve performance. Use `protocol_mode: "serial"` to force Micro800 mode and disable MSP when needed for compatibility.

See [MOCK_PLC_LIMITATIONS.md](MOCK_PLC_LIMITATIONS.md) for details on mock PLC limitations.

### Operating Modes

Both mock PLCs support the same operating modes:
- `normal`: Returns nominal values with small variance
- `degraded`: Gradually drifts toward failure thresholds
- `failed`: Returns failure condition values
- `unresponsive`: Stops responding (simulates network issues)

### Alternative Options

1. **Use a real PLC** (recommended for production testing) - Update config.yaml with your PLC IP
2. **Use a commercial PLC simulator** - FactoryTalk Linx, RSLogix Emulate, etc.
3. **Test other features** - The app will run without PLC connection, allowing you to test dashboard, API, and AAP integration

## Usage

### Web Dashboard

1. Open http://localhost:15000 in your browser
2. Monitor real-time tag values, connection status, and violations
3. View time-series charts for motor speed and light status
4. Trigger manual remediation actions
5. Enable/configure chaos injection for testing
6. View event log and AAP job status

### REST API

#### Health & Status
```bash
# Health check
curl http://localhost:15000/api/v1/health

# Get current status
curl http://localhost:15000/api/v1/status
```

#### Tags & Metrics
```bash
# Get all tag values
curl http://localhost:15000/api/v1/tags

# Get specific tag with history
curl http://localhost:15000/api/v1/tags/Motor_Speed

# Get aggregated metrics
curl http://localhost:15000/api/v1/metrics
```

#### Events
```bash
# Get recent events
curl http://localhost:15000/api/v1/events

# Get active violations
curl http://localhost:15000/api/v1/events/violations?active=true
```

#### Remediation
```bash
# Trigger emergency stop
curl -X POST http://localhost:15000/api/v1/remediate/stop

# Trigger emergency reset
curl -X POST http://localhost:15000/api/v1/remediate/reset

# Get remediation status
curl http://localhost:15000/api/v1/remediate/status
```

#### Chaos Engineering
```bash
# Get chaos status
curl http://localhost:15000/api/v1/chaos/status

# Enable chaos injection
curl -X POST http://localhost:15000/api/v1/chaos/enable

# Inject specific failure
curl -X POST http://localhost:15000/api/v1/chaos/inject \
  -H "Content-Type: application/json" \
  -d '{"failure_type": "connection_loss", "duration_seconds": 10}'
```

**Note:** When chaos injection is enabled, failure conditions (especially `value_anomaly`) persist for a random duration between 1 and 180 seconds. This simulates real-world transient failures that may resolve on their own or require remediation.

### Ansible Playbooks

The project includes Ansible playbooks for remediation actions:

```bash
# Emergency stop
ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/emergency_stop.yml

# Emergency reset
ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/emergency_reset.yml

# Gather metrics
ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/gather_metrics.yml
```

## API Documentation

### Response Format

All API responses follow this structure:

```json
{
  "success": true,
  "timestamp": "2024-01-15T10:30:00Z",
  "data": { ... },
  "error": null
}
```

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health` | Application health check |
| GET | `/api/v1/status` | PLC connection status and tag values |
| GET | `/api/v1/tags` | Current values for all tags |
| GET | `/api/v1/tags/{tag_name}` | Specific tag value and history |
| GET | `/api/v1/metrics` | Aggregated metrics |
| GET | `/api/v1/events` | Recent events (paginated) |
| GET | `/api/v1/events/violations` | Active threshold violations |
| POST | `/api/v1/remediate/{action}` | Trigger remediation (stop/reset/restart) |
| GET | `/api/v1/remediate/status` | Remediation job status |
| GET | `/api/v1/chaos/status` | Chaos engine status |
| POST | `/api/v1/chaos/enable` | Enable chaos injection |
| POST | `/api/v1/chaos/disable` | Disable chaos injection |
| POST | `/api/v1/chaos/inject` | Manually inject failure |
| GET | `/api/v1/config` | Current configuration (sanitized) |

## Development

### Project Structure

```
plc-remedy/
├── app/
│   ├── __init__.py
│   ├── config.py              # Configuration loader
│   ├── plc_client.py          # PLC communication
│   ├── aap_client.py          # AAP API integration
│   ├── monitor.py             # Polling and threshold detection
│   ├── chaos.py               # Chaos engineering
│   ├── models.py              # Data models
│   ├── api/                   # REST API
│   ├── web/                   # Web dashboard
│   └── templates/             # HTML templates
├── ansible/                   # Ansible playbooks
├── mock/                      # Mock PLC and AAP simulators
├── config/                    # Configuration files
├── tests/                     # Unit tests
├── Containerfile             # Container definition
├── requirements.txt          # Python dependencies
└── run.py                    # Application entry point
```

### Running Tests

#### Unit Tests

```bash
pytest tests/
```

#### Testing with tmux Wrapper Script

For easy testing with all components running simultaneously, use the `run_tests.sh` wrapper script. This script uses tmux to display all component logs in a single window with 3 panes (1 column, 3 rows).

**Install tmux:**

- **macOS**: `brew install tmux`
- **Linux**: `sudo apt-get install tmux` (or use your distribution's package manager)
- **Other**: See [tmux installation guide](https://github.com/tmux/tmux/wiki/Installing)

**Using the wrapper script:**

```bash
./run_tests.sh
```

This will start:
- **Top pane**: Mock PLC (port 44818)
- **Middle pane**: Mock AAP (port 8080)
- **Bottom pane**: Main application (port 15000)

All logs are visible simultaneously in the tmux window. The script prevents detaching/reattaching - when you exit tmux (Ctrl+C or closing the terminal), all components will stop automatically.

**Stopping the test environment:**

- Press `Ctrl+C` in any pane, or
- Type `exit` in any pane, or
- Close the terminal window

All processes will be cleaned up automatically when the tmux session ends.

### Code Style

The project follows PEP 8 style guidelines. Consider using `black` for code formatting:

```bash
pip install black
black app/ tests/
```

### Pre-commit Hooks

This repository uses [pre-commit](https://pre-commit.com) to automatically check code quality before commits. Pre-commit hooks validate Python, HTML, and YAML files for syntax errors.

#### Installation

1. Install pre-commit (if not already installed):
```bash
pip install pre-commit
```

Or install all development dependencies:
```bash
pip install -r requirements.txt
```

2. Install the git hooks:
```bash
pre-commit install
```

This will install hooks that run automatically on `git commit`.

#### What Gets Checked

The pre-commit hooks validate:

- **Python files** (`*.py`): Syntax checking using `pyflakes`
- **HTML files** (`*.html`): HTML5 validation using `html5validator`
- **YAML files** (`*.yaml`, `*.yml`, `*.yaml.example`, `*.yaml.test`, `*.yml.example`, `*.yml.test`):
  - Basic syntax validation using `check-yaml`
  - Comprehensive linting using `yamllint`

Additional checks:
- Trailing whitespace removal
- End of file fixes
- Merge conflict detection
- Large file detection
- JSON and TOML validation

#### Running Manually

You can run pre-commit hooks manually on all files:

```bash
# Run on all files
pre-commit run --all-files

# Run on staged files only
pre-commit run

# Run a specific hook
pre-commit run pyflakes --all-files
pre-commit run yamllint --all-files
pre-commit run html5validator --all-files
```

#### Skipping Hooks

If you need to skip pre-commit hooks for a specific commit (not recommended):

```bash
git commit --no-verify
```

**Note:** Skipping hooks should only be done in exceptional circumstances, as it bypasses important quality checks.

#### Updating Hooks

To update pre-commit hooks to their latest versions:

```bash
pre-commit autoupdate
```

This updates the hook versions in `.pre-commit-config.yaml` to the latest available versions.

## Troubleshooting

### PLC Connection Issues

1. Verify PLC IP address and network connectivity
2. Check firewall rules (CIP uses port 44818)
3. Ensure PLC slot number is correct (typically 0)
4. Review connection timeout settings

### AAP Integration Issues

1. Verify AAP base URL and authentication token
2. Check job template IDs match your AAP instance
3. Enable mock mode for testing: `mock_mode: true`
4. Review AAP API logs for errors

### Dashboard Not Updating

1. Check browser console for WebSocket connection errors
2. Verify Socket.IO server is running
3. Check application logs for errors
4. Ensure eventlet worker is used (required for Socket.IO)

## Limitations

- **Mock PLC**: The mock PLC simulator has some limitations (see [MOCK_PLC_LIMITATIONS.md](MOCK_PLC_LIMITATIONS.md)). For full CIP compatibility, use a real PLC or commercial simulator.
- **Data Persistence**: Currently uses in-memory storage. For production, consider adding SQLite or PostgreSQL persistence.
- **Single PLC**: The current implementation monitors one PLC. Multi-PLC support can be added by extending the architecture.

## Future Enhancements

- [ ] OPC UA protocol support
- [ ] Modbus TCP support
- [ ] PostgreSQL persistence layer
- [ ] Multi-PLC monitoring
- [ ] Advanced analytics and ML-based anomaly detection
- [ ] Integration with Grafana/Prometheus
- [ ] Role-based access control (RBAC)

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

[Specify your license here]

## References

- SAE Paper 26MFG-0011: "From Reactive to Proactive: Applying Data Analysis and Automation to Mitigate PLC Communication Disruptions"
- [pycomm3 Documentation](https://github.com/ottowayi/pycomm3)
- [Ansible CIP Collection](https://github.com/ansible-collections/community.cip)
- [Flask-SocketIO Documentation](https://flask-socketio.readthedocs.io/)

## Support

For issues and questions:
- Open an issue on GitHub
- Contact the development team
- Review the troubleshooting section above
