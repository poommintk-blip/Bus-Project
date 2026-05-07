import requests
import websocket
import json
import time
import threading
import os
import socket
import selectors
from datetime import datetime

# --- Configuration เดิม ---
BASE_URL = "http://203.158.3.33:8080"
WS_URL = "ws://203.158.3.33:8080/api/ws"
PUBLIC_ID = "44a00910-fa93-11ef-94ed-973314b03447"

# --- TCP Server Configuration ---
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 9000
sel = selectors.DefaultSelector() # [cite: 10, 38]

# Shared State
bus_state = {}
state_lock = threading.Lock()
token_info = {"token": None, "exp": 0}

# --- TCP Server Logic (Lab 04 Style) ---

def accept_wrapper(sock, mask):
    """รับการเชื่อมต่อจาก Client"""
    conn, addr = sock.accept()
    print(f" [+] Client Connected: {addr}")
    conn.setblocking(False) # [cite: 42, 210]
    # ลงทะเบียนเพื่อรออ่านข้อมูล (READ) และใช้ callback read_wrapper
    sel.register(conn, selectors.EVENT_READ, read_wrapper) # [cite: 43]

def read_wrapper(conn, mask):
    """อ่านคำสั่งจาก Client"""
    try:
        data = conn.recv(1024)
        if data:
            command = data.decode().strip().upper()
            if command == "LIST":
                with state_lock:
                    # ส่งข้อมูล bus_state ทั้งหมดกลับไปในรูปแบบ JSON
                    response = json.dumps(bus_state) + "\n"
                    conn.sendall(response.encode())
        else:
            print(f" [-] Client Disconnected")
            sel.unregister(conn)
            conn.close()
    except Exception as e:
        print(f" [!] Socket Error: {e}")
        sel.unregister(conn)
        conn.close()

# --- WebSocket & Token Logic (คงเดิมจากไฟล์ที่ให้มา) ---

def now_str(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def fetch_new_token():
    r = requests.post(f"{BASE_URL}/api/auth/login/public", json={"publicId": PUBLIC_ID}, timeout=15)
    token = r.json()["token"]
    token_info["token"] = token
    print(f"[{now_str()}] Token refreshed")

def on_message(ws, message):
    msg = json.loads(message)
    # รับข้อมูลแล้วเอามาใส่ merge_entity (ย่อฟังก์ชันเพื่อให้สั้นลง)
    data_list = msg.get("data", {}).get("data", []) if "data" in msg else msg.get("update", [])
    for item in data_list:
        eid = item["entityId"]["id"]
        with state_lock:
            if eid not in bus_state: bus_state[eid] = {}
            if "latest" in item: bus_state[eid].update(item["latest"])
    # (สามารถเรียก print_bus_table() ที่นี่ได้เหมือนเดิม)

def run_ws():
    fetch_new_token()
    ws = websocket.WebSocketApp(WS_URL, on_open=lambda ws: ws.send(json.dumps(build_subscribe_payload())), on_message=on_message)
    ws.run_forever(ping_interval=20)

def build_subscribe_payload():
    # ... (เนื้อหาเหมือนในไฟล์ต้นฉบับของคุณ) ...
    return {"cmds": [{"type": "ENTITY_DATA", "query": {"entityFilter": {"type": "deviceType", "deviceTypes": ["bus"]}, "pageLink": {"pageSize": 100}, "latestValues": [{"type": "TIME_SERIES", "key": "latitude"}]}, "cmdId": 1}]}

# --- Main Execution ---

if __name__ == "__main__":
    # 1. เริ่มต้น TCP Server Socket
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # [cite: 59]
    server_sock.bind((SERVER_HOST, SERVER_PORT))
    server_sock.listen()
    server_sock.setblocking(False) # [cite: 58, 209]
    sel.register(server_sock, selectors.EVENT_READ, accept_wrapper) # [cite: 65]
    print(f"[*] TCP Server running on {SERVER_HOST}:{SERVER_PORT}")

    # 2. รัน WebSocket ใน Thread แยก เพื่อไม่ให้ Block Event Loop
    threading.Thread(target=run_ws, daemon=True).start()

    # 3. Event Loop สำหรับจัดการ Client (Lab 04) [cite: 67, 68]
    try:
        while True:
            events = sel.select(timeout=1)
            for key, mask in events:
                callback = key.data
                callback(key.fileobj, mask) # [cite: 71]
    except KeyboardInterrupt:
        print("Stopping Server...")