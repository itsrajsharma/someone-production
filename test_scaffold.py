import uuid
from pipeline.scaffold_builder import build_scaffold
test_id = str(uuid.uuid4())
session_id = str(uuid.uuid4())
msg = "I'm tired"
scaffold = build_scaffold(msg, test_id, session_id, persona="aria")
print(scaffold)
