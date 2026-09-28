import requests

url = "https://hsr-data-catherinenjenjenga.aws-eu-west-1.turso.io/v2/pipeline"
headers = {"Authorization": f"Bearer {TURSO_TOKEN}"}

payload = {
    "requests": [
        {"type": "execute", "stmt": {"sql": "INSERT INTO recommendations ..."}},
        {"type": "close"}
    ]
}

requests.post(url, headers=headers, json=payload)
