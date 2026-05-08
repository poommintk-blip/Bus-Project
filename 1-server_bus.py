import requests
import websocket
import json
import time
import threading
import os
import socket
import selectors
import base64
from datetime import datetime

# --- CONFIGURATION ---
BASE_URL = "http://203.158.3.33:8080"
WS_URL = "ws://203.158.3.33:8080/api/ws"
PUBLIC_ID = "44a00910-fa93-11ef-94ed-973314b03447"
SERVER_HOST, SERVER_PORT = "0.0.0.0", 9000

# WebSocket Timing
TOKEN_REFRESH_MARGIN = 60
PING_INTERVAL = 20
PING_TIMEOUT  = 10

sel = selectors.DefaultSelector()
bus_state = {}
state_lock = threading.Lock()
token_info = {"token": None, "exp": 0}

# --- UTILITIES ---
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def decode_jwt_exp(token: str) -> int:
    try:
        parts = token.split(".")
        if len(parts) != 3: return 0
        payload = parts[1]
        padding = "=" * (-len(payload) % 4)
        import base64
        decoded = base64.urlsafe_b64decode(payload + padding)
        return int(json.loads(decoded.decode()).get("exp", 0))
    except: return 0

def fetch_new_token():
    try:
        r = requests.post(f"{BASE_URL}/api/auth/login/public", json={"publicId": PUBLIC_ID}, timeout=15)
        r.raise_for_status()
        token = r.json()["token"]
        token_info["token"] = token
        token_info["exp"] = decode_jwt_exp(token)
        print(f"[{now_str()}] 🔑 Token refreshed")
    except Exception as e:
        print(f"[{now_str()}] ❌ Token Error: {e}")

# --- TCP SERVER LOGIC (Lab 4) ---
def accept_wrapper(sock, mask):
    conn, addr = sock.accept()
    conn.setblocking(False)
    sel.register(conn, selectors.EVENT_READ, read_wrapper)
    print(f" [+] TCP Client Connected: {addr}")

def read_wrapper(conn, mask):
    try:
        data = conn.recv(1024)
        if data and data.decode().strip().upper() == "LIST":
            with state_lock:
                response = json.dumps(bus_state) + "\n"
                conn.sendall(response.encode())
        else:
            sel.unregister(conn)
            conn.close()
    except:
        try: sel.unregister(conn)
        except: pass
        conn.close()

# --- WEBSOCKET CALLBACKS ---
def build_subscribe_payload():
    keys = [{"type":"TIME_SERIES","key":k} for k in ["latitude", "longitude", "speed", "status"]]
    return {
        "cmds": [{
            "type": "ENTITY_DATA",
            "query": {
                "entityFilter": {"type": "deviceType", "deviceTypes": ["bus"]},
                "pageLink": {"pageSize": 100},
                "entityFields": [{"type": "ENTITY_FIELD", "key": "name"}],
                "latestValues": keys
            },
            "cmdId": 1
        }]
    }

def on_open(ws):
    print(f"[{now_str()}] 🌐 WebSocket Connected, sending auth...")
    # ส่ง Auth ก่อนเป็นอันดับแรกเพื่อยืนยันตัวตน
    auth_payload = {"authCmd": {"cmdId": 0, "token": token_info["token"]}}
    ws.send(json.dumps(auth_payload))
    # ส่ง Subscribe ตามทันทีเพื่อให้ได้ข้อมูลรถ
    ws.send(json.dumps(build_subscribe_payload()))
    print(f"[{now_str()}] ✅ Auth and Subscribe sent")

def on_message(ws, message):
    msg = json.loads(message)
    data_list = msg.get("data", {}).get("data", []) if "data" in msg else msg.get("update", [])
    for item in data_list:
        eid = item["entityId"]["id"]
        latest = item.get("latest", {})
        with state_lock:
            if eid not in bus_state: bus_state[eid] = {"ENTITY_FIELD": {}, "TIME_SERIES": {}}
            if "ENTITY_FIELD" in latest: bus_state[eid]["ENTITY_FIELD"].update(latest["ENTITY_FIELD"])
            if "TIME_SERIES" in latest: bus_state[eid]["TIME_SERIES"].update(latest["TIME_SERIES"])

def run_ws():
    fetch_new_token()
    ws = websocket.WebSocketApp(
        WS_URL,
        header={"Origin": BASE_URL},
        on_open=on_open,
        on_message=on_message
    )
    ws.run_forever(ping_interval=PING_INTERVAL, ping_timeout=PING_TIMEOUT)

# --- MAIN ---
if __name__ == "__main__":
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((SERVER_HOST, SERVER_PORT))
    server_sock.listen()
    server_sock.setblocking(False)
    sel.register(server_sock, selectors.EVENT_READ, accept_wrapper)
    
    # รัน WebSocket ในเธรดแยกเพื่อไม่ให้ขัดจังหวะการทำงานของ TCP Server
    threading.Thread(target=run_ws, daemon=True).start()
    print(f"[*] TCP Server running on {SERVER_HOST}:{SERVER_PORT}")

    try:
        while True:
            for key, mask in sel.select(timeout=1):
                callback = key.data
                callback(key.fileobj, mask)
    except KeyboardInterrupt:
        print("\nStopping Server...")