#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="$PROJECT_DIR/logs/update.log"

mkdir -p "$PROJECT_DIR/logs"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

cd "$PROJECT_DIR"
log "Starting update..."

log "Pulling latest changes..."
git pull 2>&1 | tee -a "$LOG_FILE"

log "Activating venv and installing dependencies..."
source "$PROJECT_DIR/venv/bin/activate"
pip install -r requirements.txt 2>&1 | tee -a "$LOG_FILE"

log "Update complete."
