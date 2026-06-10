#!/bin/bash
set -e

opendataloader-pdf-hybrid --port 5003 --ocr-engine rapidocr &
HYBRID_PID=$!

echo "Waiting for hybrid backend to start (pid $HYBRID_PID)..."
sleep 10

exec python3 /app/server.py
