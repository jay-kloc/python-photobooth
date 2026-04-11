#!/bin/bash
# Photobooth launcher script
# Usage:
#   ./run.sh              # Mock camera mode (development)
#   ./run.sh gphoto2      # Real Canon DSLR mode
#   ./run.sh mock --fullscreen   # Mock camera, fullscreen

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Set up virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Parse arguments
CAMERA_MODE="${1:-mock}"
shift 2>/dev/null || true

for arg in "$@"; do
    case "$arg" in
        --fullscreen) export PHOTOBOOTH_FULLSCREEN=1 ;;
    esac
done

export PHOTOBOOTH_CAMERA="$CAMERA_MODE"

echo "Starting photobooth (camera: $CAMERA_MODE)..."
python3 -m src.main
