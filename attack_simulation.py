import time
import requests
import sys

try:
    from generate_jwt import create_jwt
except ImportError:
    print("Error: Could not import generate_jwt. Make sure it's in the same directory.")
    sys.exit(1)

URL = "http://localhost:10000"

def send_request(caller_id, path="/", delay=0):
    jwt_token = create_jwt(caller_id)
    headers = {"Authorization": f"Bearer {jwt_token}"}
    
    url = f"{URL}{path}"
    resp = requests.get(url, headers=headers)
    
    trust_score = resp.headers.get("x-trust-score", "N/A")
    try:
        body = resp.json() if resp.text else {}
    except Exception:
        body = {}
    route = "SANDBOX" if "SANDBOX" in str(body) else "STANDARD"
    if resp.status_code != 200:
        route = f"ERROR {resp.status_code}"
        
    print(f"[{caller_id}] {path} -> Route: {route} | Trust Score: {trust_score}")
    
    if delay > 0:
        time.sleep(delay)

print("="*50)
print("SCENARIO 1: Normal Traffic")
print("="*50)
for i in range(5):
    send_request("order-service", delay=1)

print("\n" + "="*50)
print("SCENARIO 2: Burst Attack")
print("="*50)
for i in range(15):
    send_request("suspicious-service", delay=0)

print("\n" + "="*50)
print("SCENARIO 3: Sensitive Endpoint Probe")
print("="*50)
for i in range(3):
    send_request("order-service", path="/admin", delay=0.5)

print("\nSimulation complete!")
