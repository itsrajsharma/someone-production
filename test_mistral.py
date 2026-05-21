import os
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("MISTRAL_API_KEY", "").strip()
print(f"Key starts with: {api_key[:5] if api_key else 'None'}")

url = "https://api.mistral.ai/v1/embeddings"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}
payload = {
    "model": "mistral-embed",
    "input": ["test"]
}

response = requests.post(url, json=payload, headers=headers)
print(f"Status: {response.status_code}")
print(f"Response: {response.text}")
