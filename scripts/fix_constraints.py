"""Add missing unique constraints needed for upsert operations."""
import os, requests
from dotenv import load_dotenv

load_dotenv()

url = os.environ["SUPABASE_URL"]
service_key = os.environ["SUPABASE_KEY"]

sql = """
-- Add composite unique constraints required for upsert on_conflict
ALTER TABLE turns        ADD CONSTRAINT turns_id_user_id_key        UNIQUE (id, user_id);
ALTER TABLE open_stories ADD CONSTRAINT open_stories_story_user_key  UNIQUE (story_id, user_id);
ALTER TABLE tensions     ADD CONSTRAINT tensions_id_user_key         UNIQUE (tension_id, user_id);
"""

resp = requests.post(
    f"{url}/rest/v1/rpc/exec_sql",
    headers={
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    },
    json={"query": sql},
)
# exec_sql doesn't exist — use the SQL endpoint directly
print("Using direct SQL via postgres...")

# Run via auth/v1 admin won't work either; use pg connection
# Easiest: use supabase-py to run raw SQL
from supabase import create_client
db = create_client(url, service_key)

statements = [
    "ALTER TABLE turns ADD CONSTRAINT IF NOT EXISTS turns_id_user_id_key UNIQUE (id, user_id)",
    "ALTER TABLE open_stories ADD CONSTRAINT IF NOT EXISTS open_stories_story_user_key UNIQUE (story_id, user_id)", 
    "ALTER TABLE tensions ADD CONSTRAINT IF NOT EXISTS tensions_id_user_key UNIQUE (tension_id, user_id)",
]

for stmt in statements:
    try:
        result = db.rpc("exec", {"sql": stmt}).execute()
        print(f"OK: {stmt[:60]}")
    except Exception as e:
        print(f"Error: {e}")
        
print("Done")
