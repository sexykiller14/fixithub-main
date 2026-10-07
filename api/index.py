"""Vercel Serverless Function entrypoint for FixIT Hub."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add project root directory to sys.path so app modules are discoverable
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Mark that the app is executing inside Vercel / serverless runtime
os.environ.setdefault("VERCEL", "1")

from app.main import app

# Export the ASGI application for @vercel/python
__all__ = ["app"]
