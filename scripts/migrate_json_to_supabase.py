"""
migrate_json_to_supabase.py
One-shot migration of all legacy JSON data files into Supabase tables.
Safe to run multiple times — uses upsert/insert-if-not-exists logic.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent))

from db.client import get_db

DATA_DIR = Path(__file__).parent.parent / "data"
# Your Supabase user_id (from create_auth_user.py output)
USER_ID = "9650ca29-2be6-4d30-846b-42f25e70def4"
ARIA_PERSONA   = "aria"
ORACLE_PERSONA = "oracle"

db = get_db()

# ── Helpers ────────────────────────────────────────────────────────────────────

def load_json(filename):
    path = DATA_DIR / filename
    if not path.exists():
        print(f"  [skip] {filename} not found")
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def chunked(lst, size=100):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]

# ── 1. TURNS ──────────────────────────────────────────────────────────────────

def migrate_turns():
    print("\n[1/8] Migrating turns (aria)...")
    turns = load_json("turns.json")
    if not turns:
        return

    rows = []
    for t in turns:
        rows.append({
            "id":         t["id"],
            "user_id":    USER_ID,
            "persona":    ARIA_PERSONA,
            "role":       t["role"],
            "content":    t["content"],
            "timestamp":  t.get("timestamp", datetime.utcnow().isoformat()),
            "causal_tags": t.get("causal_tags", {}),
        })

    # Clear any existing test rows first
    db.table("turns").delete().eq("user_id", USER_ID).eq("persona", ARIA_PERSONA).execute()

    inserted = 0
    for batch in chunked(rows):
        db.table("turns").insert(batch).execute()
        inserted += len(batch)
    print(f"  -> {inserted} aria turns migrated")

    # Oracle turns
    print("  Migrating turns (oracle)...")
    oracle_turns = load_json("oracle_turns.json")
    if oracle_turns:
        orows = []
        for i, t in enumerate(oracle_turns):
            orows.append({
                "id":         t.get("id", f"orc_{i:04d}"),
                "user_id":    USER_ID,
                "persona":    ORACLE_PERSONA,
                "role":       t["role"],
                "content":    t["content"],
                "timestamp":  t.get("timestamp", datetime.utcnow().isoformat()),
                "causal_tags": t.get("causal_tags", {}),
            })
        db.table("turns").delete().eq("user_id", USER_ID).eq("persona", ORACLE_PERSONA).execute()
        for batch in chunked(orows):
            db.table("turns").insert(batch).execute()
        print(f"  -> {len(orows)} oracle turns migrated")

# ── 2. EBF ────────────────────────────────────────────────────────────────────

def migrate_ebf():
    print("\n[2/8] Migrating EBF...")
    ebf = load_json("ebf.json")
    if not ebf:
        return

    row = {
        "user_id":                   USER_ID,
        "persona":                   ARIA_PERSONA,
        "dominant_emotion_pattern":  ebf.get("dominant_emotion_pattern", "unknown"),
        "communication_style":       ebf.get("communication_style", "neutral"),
        "trust_level":               ebf.get("trust_level", 0.10),
        "current_state":             ebf.get("current_state", "neutral"),
        "unmet_need":                ebf.get("unmet_need", ""),
        "response_preference":       ebf.get("response_preference", "balanced"),
        "session_message_count":     ebf.get("session_message_count", 0),
        "total_message_count":       ebf.get("total_message_count", 0),
        "energy_level":              ebf.get("energy_level", "medium"),
        "last_updated":              ebf.get("last_updated", datetime.utcnow().isoformat()),
    }
    db.table("ebf").upsert(row, on_conflict="user_id,persona").execute()
    print(f"  -> EBF migrated (trust={row['trust_level']:.2f})")

# ── 3. SNAPSHOTS ──────────────────────────────────────────────────────────────

def migrate_snapshots():
    print("\n[3/8] Migrating snapshots...")
    snapshots = load_json("snapshots.json")
    if not snapshots:
        return

    rows = []
    for s in snapshots:
        rows.append({
            "user_id":               USER_ID,
            "persona":               ARIA_PERSONA,
            "date":                  s.get("date", datetime.utcnow().strftime("%Y-%m-%d")),
            "time_of_day":           s.get("time_of_day", "unknown"),
            "facts_learned":         s.get("facts_learned", []),
            "emotional_tone":        s.get("emotional_tone", "neutral"),
            "energy_level":          s.get("energy_level", "medium"),
            "events":                s.get("events", []),
            "open_stories":          s.get("open_stories", []),
            "behaviour_signal":      s.get("behaviour_signal", ""),
            "communication_style":   s.get("communication_style", "neutral"),
            "trust_level_at_snapshot": s.get("trust_level_at_snapshot", 0.1),
        })

    for batch in chunked(rows):
        db.table("snapshots").insert(batch).execute()
    print(f"  -> {len(rows)} snapshots migrated")

# ── 4. OPEN STORIES ───────────────────────────────────────────────────────────

def migrate_open_stories():
    print("\n[4/8] Migrating open stories...")
    stories = load_json("open_stories.json")
    if not stories:
        return

    rows = []
    for s in stories:
        rows.append({
            "story_id":   s.get("id", s.get("story_id", "")),
            "user_id":    USER_ID,
            "persona":    ARIA_PERSONA,
            "title":      s.get("title", ""),
            "status":     s.get("status", "open"),
            "first_told": s.get("first_told", datetime.utcnow().isoformat()),
            "last_told":  s.get("last_told", datetime.utcnow().isoformat()),
            "summary":    s.get("summary", ""),
            "resolved_at": s.get("resolved_at"),
        })

    db.table("open_stories").delete().eq("user_id", USER_ID).execute()
    db.table("open_stories").insert(rows).execute()
    print(f"  -> {len(rows)} open stories migrated")

# ── 5. TENSIONS ───────────────────────────────────────────────────────────────

def migrate_tensions():
    print("\n[5/8] Migrating tensions...")
    tensions = load_json("tensions.json")
    if not tensions:
        return

    rows = []
    for t in tensions:
        rows.append({
            "tension_id": t.get("id", ""),
            "user_id":    USER_ID,
            "persona":    ARIA_PERSONA,
            "type":       t.get("type", "unknown"),
            "summary":    t.get("summary", ""),
            "status":     t.get("status", "open"),
            "created_at": t.get("created_at", datetime.utcnow().isoformat()),
            "resolved_at": t.get("resolved_at"),
        })

    db.table("tensions").delete().eq("user_id", USER_ID).execute()
    db.table("tensions").insert(rows).execute()
    print(f"  -> {len(rows)} tensions migrated")

# ── 6. BEHAVIOUR RHYTHM ───────────────────────────────────────────────────────

def migrate_rhythm():
    print("\n[6/8] Migrating behaviour rhythm...")
    rhythm = load_json("rhythm.json")
    if not rhythm:
        return

    row = {
        "user_id":               USER_ID,
        "persona":               ARIA_PERSONA,
        "most_open_time":        rhythm.get("most_open_time", "unknown"),
        "most_stressed_day":     rhythm.get("most_stressed_day", "unknown"),
        "storytelling_frequency": rhythm.get("storytelling_frequency", "unknown"),
        "trust_growth_rate":     rhythm.get("trust_growth_rate", "unknown"),
        "session_times":         rhythm.get("session_times", []),
        "snapshot_count":        rhythm.get("snapshot_count", 0),
        "last_updated":          datetime.utcnow().isoformat(),
    }
    db.table("behaviour_rhythm").upsert(row, on_conflict="user_id,persona").execute()
    print(f"  -> Behaviour rhythm migrated (snapshot_count={row['snapshot_count']})")

# ── 7. CORE IDENTITY ──────────────────────────────────────────────────────────

def migrate_identity():
    print("\n[7/8] Migrating core identity...")
    identity = load_json("core_identity.json")
    if not identity:
        return

    row = {
        "user_id":                        USER_ID,
        "snapshot_count_at_last_update":  identity.get("snapshot_count_at_last_update", 0),
        "psychological_profile":          identity.get("psychological_profile", ""),
        "current_life_chapter":           identity.get("current_life_chapter", ""),
        "enduring_traits":                identity.get("enduring_traits", []),
        "last_updated":                   datetime.utcnow().isoformat(),
    }
    db.table("core_identity").upsert(row, on_conflict="user_id").execute()
    print(f"  -> Core identity migrated")
    print(f"     Chapter: {row['current_life_chapter'][:60]}...")

# ── 8. HEALTH REPORT ──────────────────────────────────────────────────────────

def migrate_health():
    print("\n[8/8] Migrating health report...")
    health = load_json("health_report.json")
    if not health:
        return

    row = {
        "user_id":               USER_ID,
        "week_summary":          health.get("week_summary", {}),
        "anomalies":             health.get("anomalies", []),
        "compared_to_last_week": health.get("compared_to_last_week"),
    }
    db.table("health_reports").insert(row).execute()
    print(f"  -> Health report migrated")

# ── Run all ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  Someone v1 -- JSON -> Supabase Migration")
    print(f"  User ID: {USER_ID}")
    print(f"  Data dir: {DATA_DIR}")
    print("=" * 55)

    migrate_turns()
    migrate_ebf()
    migrate_snapshots()
    migrate_open_stories()
    migrate_tensions()
    migrate_rhythm()
    migrate_identity()
    migrate_health()

    print("\n" + "=" * 55)
    print("  Migration complete.")
    print("=" * 55)

    # Verify row counts
    print("\nVerifying counts in Supabase:")
    for table in ["turns", "ebf", "snapshots", "open_stories", "tensions", "behaviour_rhythm", "core_identity", "health_reports"]:
        res = db.table(table).select("*", count="exact").eq("user_id", USER_ID).execute()
        print(f"  {table:<22} {res.count} rows")
