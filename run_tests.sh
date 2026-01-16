#!/bin/bash
# Wrapper script to run all test components in tmux for easy log viewing
# This script starts the mock PLC, mock AAP, and main application in separate tmux panes

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Session name
SESSION_NAME="plc-test"

# Function to print colored messages
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    print_error "tmux is not installed. Please install it first:"
    echo "  macOS: brew install tmux"
    echo "  Linux: sudo apt-get install tmux  # or use your package manager"
    exit 1
fi

# Check if we're in the right directory
if [ ! -f "run.py" ] || [ ! -d "mock" ]; then
    print_error "This script must be run from the project root directory"
    exit 1
fi

# Check if config/config.yaml exists
if [ ! -f "config/config.yaml" ]; then
    print_error "config/config.yaml does not exist. Please create it first."
    exit 1
fi

# Check if conda plc-remedy environment exists
if ! conda env list | grep -q "plc-remedy"; then
    print_error "conda plc-remedy environment does not exist. Please create it first."
    exit 1
fi

# Check if conda plc-remedy environment is active (CONDA_DEFAULT_ENV is set to plc-remedy)
if ! test "$CONDA_DEFAULT_ENV" = "plc-remedy"; then
    print_error "conda plc-remedy environment is not active. Please activate it first."
    exit 1
fi

# Check if Python is available
if ! command -v python &> /dev/null && ! command -v python3 &> /dev/null; then
    print_error "Python is not installed or not in PATH"
    exit 1
fi

# Determine Python command
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    print_error "Could not find Python executable"
    exit 1
fi

# Cleanup function to kill tmux session and all processes
cleanup() {
    print_info "Cleaning up..."
    # Kill the tmux session (this will kill all processes in it)
    tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true
    print_info "All test components stopped"
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM EXIT

# Check if session already exists
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    print_warning "Session '$SESSION_NAME' already exists. Killing it first..."
    tmux kill-session -t "$SESSION_NAME"
fi

print_info "Starting test components in tmux session '$SESSION_NAME'..."

# Create new tmux session in detached mode
# Start with the mock PLC in the first pane
tmux new-session -d -s "$SESSION_NAME" -x 120 -y 40 \
    "$PYTHON_CMD mock/cip_plc.py --ip 127.0.0.1 --port 44818 --mode normal"

# Set pane title for pane 0 (Mock PLC)
tmux select-pane -t "$SESSION_NAME:0.0" -T "Mock PLC"
sleep 5

# Split window vertically to create second pane (Mock AAP)
tmux split-window -v -t "$SESSION_NAME:0.0" \
    "$PYTHON_CMD mock/mock_aap.py"

# Set pane title for pane 1 (Mock AAP)
tmux select-pane -t "$SESSION_NAME:0.1" -T "Mock AAP"
sleep 5

# Split the bottom pane (pane 1) vertically to create third pane (Main App)
tmux split-window -v -t "$SESSION_NAME:0.1" \
    "$PYTHON_CMD run.py"

# Set pane title for pane 2 (Main App)
tmux select-pane -t "$SESSION_NAME:0.2" -T "Main Application"

# Set layout to even-vertical to ensure all panes are equal size
tmux select-layout -t "$SESSION_NAME:0" even-vertical

# Configure tmux to prevent detaching
# Set detach-on-destroy to ensure processes stop when session ends
tmux set-option -t "$SESSION_NAME" -g detach-on-destroy on

# Select the first pane (top) for initial focus
tmux select-pane -t "$SESSION_NAME:0.0"

# Display instructions
print_info "Test components started in tmux session '$SESSION_NAME'"
echo ""
echo "Layout:"
echo "  ┌─────────────────────────┐"
echo "  │   Mock PLC (Port 44818)  │"
echo "  ├─────────────────────────┤"
echo "  │   Mock AAP (Port 8080)   │"
echo "  ├─────────────────────────┤"
echo "  │   Main App (Port 15000)  │"
echo "  └─────────────────────────┘"
echo ""
echo "To exit: Press Ctrl+C or type 'exit' in any pane"
echo "Closing tmux will stop all components"
echo ""

# Attach to the session (non-detachable)
# This will block until the session is closed
tmux attach-session -t "$SESSION_NAME"

# Cleanup will be called via trap when script exits
