"""Create the Supabase Auth user for Raj."""
import os, requests
from dotenv import load_dotenv

load_dotenv()

url = os.environ["SUPABASE_URL"]
service_key = os.environ["SUPABASE_KEY"]

resp = requests.post(
    f"{url}/auth/v1/admin/users",
    headers={
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    },
    json={
        "email": "itsrajsharma29@gmail.com",
        "password": "D^c/t$b9ZB879a_",
        "email_confirm": True,
    },
)
print("Status:", resp.status_code)
data = resp.json()
if "id" in data:
    print("User ID:", data["id"])
    print("Email:", data["email"])
    print("Auth user created successfully!")
else:
    print("Response:", data)
