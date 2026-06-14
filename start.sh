#!/bin/bash
set -e

echo "=== DIAGNOSTICS ==="
echo "PATH: $PATH"
echo "python3 location: $(which python3)"
echo "python3 version: $(python3 --version)"
echo "pip location: $(which pip)"
echo "pip version: $(pip --version 2>/dev/null || python3 -m pip --version)"
echo "Installed packages:"
python3 -m pip list || echo "failed to list packages"
echo "==================="

opendataloader-pdf-hybrid --port 5003 --ocr-engine rapidocr &
HYBRID_PID=$!

echo "Waiting for hybrid backend to start (pid $HYBRID_PID)..."
sleep 10

exec python3 /app/server.py
