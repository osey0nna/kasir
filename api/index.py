import os
import sys

# Entry point Vercel (serverless). Objek `app` dikenali otomatis oleh runtime Python.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402,F401
