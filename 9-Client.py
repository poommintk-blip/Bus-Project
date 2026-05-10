import requests
import websocket
import json
import time
import threading
import socket
import os
import selectors
from datetime import datetime

# --- CONFIGURATION ---
BASE_URL = "http://203.158.3.33:8080"
WS_URL = "ws://203.158.3.33:8080/api/ws"
PUBLIC_ID = "44a00910-fa93-11ef-94ed-973314b03447"
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 9999

sel = selectors.DefaultSelector() # [cite: 38]
tcp_clients = set() 
bus_state = {}
state_lock = threading.Lock()
token_info = {"token": None, "exp": 0}

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# --- TCP SERVER CALLBACKS (LAB 4 Style) --- [cite: 27, 39]

def accept_wrapper(sock, mask):
    conn, addr = sock.accept() # [cite: 40]
    print(f" [+] TCP Client Connected: {addr}")
    conn.setblocking(False) # [cite: 42, 206]
    tcp_clients.add(conn)
    # ลงทะเบียนเพื่อรออ่านคำสั่งจาก Client [cite: 43]
    sel.register(conn, selectors.EVENT_READ, read_wrapper)

def read_wrapper(conn, mask):
    try:
        data = conn.recv(1024) # [cite: 47]
        if data:
            cmd = data.decode().strip().upper()
            if cmd == "LIST":
                with state_lock:
                    response = json.dumps(bus_state) + "\n"
                    conn.sendall(response.encode())
        else:
            disconnect_client(conn)
    except Exception:
        disconnect_client(conn)

def disconnect_client(conn):
    if conn in tcp_clients:
        tcp_clients.remove(conn)
    sel.unregister(conn) # [cite: 52]
    conn.close() # [cite: 53]

# --- WEBSOCKET LOGIC ---

def on_message(ws, message):
    msg = json.loads(message)
    # ... ประมวลผลข้อมูลรถ (Merge Entity) ...
    # ส่งข้อมูลอัปเดตไปให้ TCP Client ทุกคน (Broadcast) [cite: 223, 248]
    update_msg = (json.dumps(msg) + "\n").encode()
    for client in tcp_clients.copy():
        try:
            client.sendall(update_msg)
        except:
            disconnect_client(client)

def run_forever(): # ฟังก์ชันที่เกิด Error ก่อนหน้านี้
    while True:
        try:
            # ตรวจสอบ Token และสร้าง WebSocketApp เชื่อมต่อ ThingsBoard
            # (ใส่ Logic WebSocket เดิมของคุณที่นี่)
            print(f"[{now_str()}] WebSocket Thread Starting...")
            # ... โค้ด WebSocketApp.run_forever() ...
            break # ตัวอย่างสั้นๆ
        except Exception as e:
            time.sleep(3)

# --- MAIN EXECUTION ---

if __name__ == "__main__":
    # 1. Setup TCP Server Socket [cite: 57]
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # [cite: 59]
    server_sock.bind((SERVER_HOST, SERVER_PORT))
    server_sock.listen()
    server_sock.setblocking(False) # [cite: 58, 209]
    
    # 2. Register Server ใน Selector [cite: 65]
    sel.register(server_sock, selectors.EVENT_READ, accept_wrapper)
    print(f"[*] TCP Server running on {SERVER_HOST}:{SERVER_PORT}")

    # 3. รัน WebSocket ใน Thread แยก (เพื่อไม่ให้ block Event Loop ของ Server)
    ws_thread = threading.Thread(target=run_forever, daemon=True)
    ws_thread.start()

    # 4. Event Loop สำหรับจัดการ TCP Clients (LAB 4 Style) [cite: 67]
    try:
        while True:
            events = sel.select(timeout=1) # [cite: 68]
            for key, mask in events:
                callback = key.data # [cite: 70]
                callback(key.fileobj, mask) # [cite: 71]
    except KeyboardInterrupt:
        print("Stopping...")