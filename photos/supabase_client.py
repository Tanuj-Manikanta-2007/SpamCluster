import os
from pathlib import Path

from supabase import create_client



try:
    from dotenv import load_dotenv 

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not url or not key:
    raise RuntimeError(
        "Missing Supabase configuration. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in environment (or .env)."
    )

supabase = create_client(url, key)
