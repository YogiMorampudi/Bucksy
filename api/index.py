"""
Vercel serverless entry point.
Vercel's @vercel/python builder looks for a WSGI `app` object in this module.
"""
import sys
from pathlib import Path

# Ensure the project root is on the import path so Flask finds templates & modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import app

# Vercel expects the WSGI callable to be named `app` — already satisfied.
