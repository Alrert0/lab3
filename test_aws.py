import requests

LEADER_URL = "http://18.209.55.154:5000/submit"

payload = {"command": "SET x=100"}

try:
    print(f"Sending to {LEADER_URL}...")
    response = requests.post(LEADER_URL, json=payload, timeout=5)

    if response.status_code == 200:
        print("SUCCESS!")
        print("Response:", response.json())
    else:
        print("FAILED!")
        print("Status Code:", response.status_code)
        print("Text:", response.text)
except Exception as e:
    print("Error:", e)

