"""End-to-end test: login → status → chat"""
import requests, json

BASE = "http://127.0.0.1:5000"

# Login
r = requests.post(f"{BASE}/auth/login", json={
    "email": "itsrajsharma29@gmail.com",
    "password": "D^c/t$b9ZB879a_",
})
data = r.json()
print("Login:", data["status"])
print("User ID:", data["user_id"])
token = data["access_token"]
session = data["session_id"]

headers = {
    "Authorization": f"Bearer {token}",
    "X-Session-ID": session,
    "Content-Type": "application/json",
}

# Status
r = requests.get(f"{BASE}/status", headers=headers)
print("\nStatus:", r.json())

# Quick intro
r = requests.get(f"{BASE}/intro/aria", headers=headers)
intro = r.json()
print("\nAria intro:", intro["reply"][:80], "...")
print("\nAll tests passed!")
