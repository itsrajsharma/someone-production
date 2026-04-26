import random
from dotenv import load_dotenv
load_dotenv(override=True)
from db.client import get_db

db = get_db()
result = db.table('core_identity').select('user_id').limit(1).execute()
uid = result.data[0]['user_id']

turns = db.table('turns').select('content, timestamp').eq('user_id', uid).eq('role', 'user').neq('content', '').execute()

sample = random.sample(turns.data, min(50, len(turns.data)))
for t in sample:
    if len(t['content']) > 30:
        print(f"[{t.get('timestamp')}] {t.get('content')}")
