"""Inspect Supabase JWT algorithm to fix token verification."""
import os, requests, base64, json
from dotenv import load_dotenv

load_dotenv()

r = requests.post(
    os.environ["SUPABASE_URL"] + "/auth/v1/token?grant_type=password",
    headers={"apikey": os.environ["SUPABASE_KEY"], "Content-Type": "application/json"},
    json={"email": "itsrajsharma29@gmail.com", "password": "D^c/t$b9ZB879a_"},
)
data = r.json()
token = data.get("access_token", "")
if token:
    header_b64 = token.split(".")[0]
    header_b64 += "=" * (4 - len(header_b64) % 4)
    header = json.loads(base64.b64decode(header_b64))
    print("JWT Header:", json.dumps(header, indent=2))
    # Also try decoding with PyJWT directly
    import jwt as pyjwt
    secret = os.environ["SUPABASE_JWT_SECRET"]
    try:
        decoded = pyjwt.decode(token, secret, algorithms=["HS256"], options={"verify_aud": False})
        print("Decoded OK with HS256, sub =", decoded.get("sub"))
    except Exception as e:
        print("HS256 failed:", e)
    try:
        decoded = pyjwt.decode(token, secret, algorithms=["RS256"], options={"verify_aud": False})
        print("Decoded OK with RS256, sub =", decoded.get("sub"))
    except Exception as e:
        print("RS256 failed:", e)
else:
    print("Login failed:", data)
