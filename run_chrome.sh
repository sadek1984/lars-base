#!/bin/bash

# Kill any existing streamlit processes (optional, helps avoid port conflicts)
pkill -f "streamlit run" || true

# Open Chrome after a slight delay (waiting for server to start)
(sleep 2 && open -a "Google Chrome" "http://localhost:8501") &

# Start Streamlit without opening the default browser
echo "🚀 Starting LARS in Google Chrome..."
streamlit run src/LARS/app.py --server.headless true
