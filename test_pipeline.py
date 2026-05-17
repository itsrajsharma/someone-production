import uuid
from pipeline.orchestrator import run_pipeline

test_id = str(uuid.uuid4())
session_id = str(uuid.uuid4())

messages = [
    "hey",
    "tired",
    "my colleague Priya helped me today, she's really smart",
    "I finally finished that thing",
    "nothing, just a boring day",
    "any i\\other llms you eany to uggesy me"
]

print("--- PIPELINE TEST START ---")
for m in messages:
    print(f"\nUSER: {m}")
    try:
        reply = run_pipeline(m, test_id, session_id, persona="aria")
        print(f"ARIA: {reply}")
    except Exception as e:
        print(f"ERROR: {e}")
print("\n--- PIPELINE TEST END ---")
