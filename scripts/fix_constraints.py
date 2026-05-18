"""Add missing unique constraints needed for upsert operations."""
import os, requests
from dotenv import load_dotenv

load_dotenv()

url = os.environ["SUPABASE_URL"]
service_key = os.environ["SUPABASE_KEY"]

print("Using direct SQL via postgres...")
from supabase import create_client
db = create_client(url, service_key)

statements = [
    "ALTER TABLE turns ADD CONSTRAINT IF NOT EXISTS turns_id_user_id_key UNIQUE (id, user_id)",
    "ALTER TABLE open_stories ADD CONSTRAINT IF NOT EXISTS open_stories_story_user_key UNIQUE (story_id, user_id)", 
    "ALTER TABLE tensions ADD CONSTRAINT IF NOT EXISTS tensions_id_user_key UNIQUE (tension_id, user_id)",
    "ALTER TABLE ebf ADD CONSTRAINT IF NOT EXISTS ebf_user_persona_key UNIQUE (user_id, persona)",
    "ALTER TABLE aria_self ADD CONSTRAINT IF NOT EXISTS aria_self_user_persona_key UNIQUE (user_id, persona)",
    "ALTER TABLE relationship_state ADD CONSTRAINT IF NOT EXISTS relationship_state_user_persona_key UNIQUE (user_id, persona)",
]

for stmt in statements:
    try:
        result = db.rpc("exec", {"sql": stmt}).execute()
        print(f"OK: {stmt[:60]}")
    except Exception as e:
        print(f"Error: {e}")
        
print("Done")
