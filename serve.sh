#!/usr/bin/env bash
# Serve the demo locally. Open http://localhost:8000/ui/ in a browser.
cd "$(dirname "$0")"
PORT="${1:-8000}"
echo "Metro Parcel Network x AlphaEvolve demo -> http://localhost:${PORT}/ui/"
exec python3 -m http.server "${PORT}"
