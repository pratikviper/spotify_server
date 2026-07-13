"""Central configuration, loaded from environment variables (with dev-friendly
defaults). Importing this module also loads a local .env file if present.
"""
import os

try:
    # Optional: load a .env file for local development.
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    # python-dotenv not installed — env vars still work, just no .env file.
    pass

# --- Auth ---
JWT_SECRET = os.environ.get('JWT_SECRET', 'password_key')

# --- Database ---
DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://postgres:test1234@localhost:5432/fluttermusicapp',
)
