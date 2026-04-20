"""
Single-command startup for KmartBot v2.

Usage (run from project root with the venv active):
    source .venv/bin/activate
    python run.py              # starts backend only (use `npm run dev` in /dashboard for dev UI)
    python run.py --build-ui   # builds the Vite dashboard first, then serves it from backend

The backend is always started. In production mode (--build-ui), the dashboard is
served as static files by FastAPI from dashboard/dist/.
"""

import argparse
import subprocess
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).parent
DASHBOARD = ROOT / "dashboard"


def build_ui() -> None:
    print("Building dashboard...")
    result = subprocess.run(["npm", "run", "build"], cwd=DASHBOARD)
    if result.returncode != 0:
        print("Dashboard build failed.")
        sys.exit(1)
    print("Dashboard built.")


def main() -> None:
    parser = argparse.ArgumentParser(description="KmartBot v2")
    parser.add_argument("--build-ui", action="store_true", help="Build Vite dashboard before starting")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--reload", action="store_true", help="Enable hot-reload (dev mode)")
    args = parser.parse_args()

    if args.build_ui:
        build_ui()

    print(f"Starting KmartBot backend on http://localhost:{args.port}")
    if not args.build_ui:
        print("  Dashboard (dev): cd dashboard && npm run dev")

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
