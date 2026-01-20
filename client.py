import requests
import sys

# Если узел A - лидер, отправляем ему. Если нет - он вернет ошибку, попробуем другой.
NODES = [
    "http://localhost:5000",
    "http://localhost:5001",
    "http://localhost:5002"
]

def send_command(cmd):
    print(f"Sending command: '{cmd}'")
    for node in NODES:
        try:
            url = f"{node}/submit"
            resp = requests.post(url, json={"command": cmd}, timeout=1)
            if resp.status_code == 200:
                print(f"Success! Response from {node}: {resp.json()}")
                return
            else:
                print(f"Node {node} is not leader...")
        except:
            print(f"Node {node} is down.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python client.py <command>")
        print("Example: python client.py 'SET x=10'")
    else:
        command = " ".join(sys.argv[1:])
        send_command(command)