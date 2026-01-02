#!/bin/bash

# Balancer Tracker - Cron Job Wrapper
# Runs daily at 7:30 AM to fetch Balancer pool data and Aura yields

# Set script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Log file for cron output
LOG_FILE="$SCRIPT_DIR/logs/cron_balancer_tracker.log"
ERROR_LOG="$SCRIPT_DIR/logs/cron_balancer_tracker_error.log"

# Create logs directory if it doesn't exist
mkdir -p "$SCRIPT_DIR/logs"

# Function to log messages
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# Function to log errors
log_error() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: $1" | tee -a "$ERROR_LOG"
}

# Start execution
log_message "Starting Balancer Tracker cron job"

# Change to project directory
cd "$SCRIPT_DIR" || {
    log_error "Failed to change to project directory: $SCRIPT_DIR"
    exit 1
}

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    log_error "Python3 is not installed or not in PATH"
    exit 1
fi

# Check if required files exist
if [ ! -f "balancer_tracker.py" ]; then
    log_error "Main script not found: balancer_tracker.py"
    exit 1
fi

if [ ! -f "Google Credentials.json" ]; then
    log_error "Google credentials not found: Google Credentials.json"
    exit 1
fi

# Run the balancer tracker with sheets export
log_message "Executing Balancer Tracker..."
python3 balancer_tracker.py --export-sheets >> "$LOG_FILE" 2>&1

# Check exit status
if [ $? -eq 0 ]; then
    log_message "Balancer Tracker completed successfully"
else
    log_error "Balancer Tracker failed with exit code $?"
    exit 1
fi

log_message "Cron job completed"
