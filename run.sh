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

# Release the camera from gvfs so gphoto2 can claim it
if [ "$CAMERA_MODE" = "gphoto2" ]; then
    if pkill -f gvfsd-gphoto2 2>/dev/null; then
        echo "Released camera from gvfs"
        sleep 1
    fi
fi

echo "Starting photobooth (camera: $CAMERA_MODE)..."
python3 -m src.main
