import requests
import websocket
import json
import time
import threading
import os
import smtplib
import math
import sqlite3
import base64
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ─── CONFIGURATION ──────────────────────────────────────────────────────────
BASE_URL   = "http://203.158.3.33:8080"
WS_URL     = "ws://203.158.3.33:8080/api/ws"
PUBLIC_ID  = "44a00910-fa93-11ef-94ed-973314b03447"
DB_NAME    = "bus_alert.db"

# Email settings (Gmail App Password)
SMTP_HOST      = "smtp.gmail.com"
SMTP_PORT      = 587
EMAIL_SENDER   = "poommin.tk@gmail.com"
EMAIL_PASSWORD = "uvta yuyz ylah ovws"

# ─── TIMING CONFIG ──────────────────────────────────────────────────────────
STOP_CONFIRM_SECONDS    = 10
DEPART_CONFIRM_SECONDS  = 10
NOTIFY_COOLDOWN_SECONDS = 360
TOKEN_REFRESH_MARGIN    = 60
PING_INTERVAL           = 20
PING_TIMEOUT            = 10

# ─── GLOBAL STATE ────────────────────────────────────────────────────────────
bus_state         = {}   # entity_id -> entity data
departure_tracker = {}   # entity_id -> state tracking dict
token_info        = {"token": None, "exp": 0}
state_lock        = threading.Lock()
ws_app            = None

# ─────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def decode_jwt_exp(token: str) -> int:
    try:
        parts = token.split(".")
        if len(parts) != 3: return 0
        payload = parts[1]
        padding = "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload + padding)
        return int(json.loads(decoded.decode()).get("exp", 0))
    except: return 0

# ─────────────────────────────────────────────
# DATABASE FUNCTIONS
# ─────────────────────────────────────────────
def get_subscribers_from_db(bus_name):
    """ดึงรายชื่ออีเมลผู้ใช้ที่เปิดรับการแจ้งเตือน (active = 1) จากตาราง users"""
    emails = []
    try:
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        cursor = conn.cursor()
        # ดึงอีเมลของผู้ใช้ที่ล็อกอินและเปิดสถานะ 'รับแจ้งเตือน' ไว้ในระบบเว็บ
        cursor.execute("SELECT email FROM users WHERE active = 1")
        emails = [row[0] for row in cursor.fetchall()]
        conn.close()
    except Exception as e:
        print(f"[{now_str()}] ❌ Database Read Error: {e}")
    return emails

def save_notification_to_db(bus_name, message):
    """บันทึกประวัติการแจ้งเตือนลงตาราง notifications เพื่อแสดงผลบนหน้าเว็บ"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO notifications (bus_name, message, sent_at) 
            VALUES (?, ?, ?)
        """, (bus_name, message, now_str()))
        conn.commit()
        conn.close()
        print(f"[{now_str()}] 💾 บันทึกประวัติการแจ้งเตือน: {bus_name}")
    except Exception as e:
        print(f"[{now_str()}] ❌ Database Save Error: {e}")

# ─────────────────────────────────────────────
# EMAIL & NOTIFICATION LOGIC
# ─────────────────────────────────────────────
def send_email_to_subscribers(bus_name, label, lat, lon, route, seats, status, notif_type="departing"):
    recipients = get_subscribers_from_db(bus_name)
    if not recipients: return

    maps_link = f"https://www.google.com/maps?q={lat},{lon}"
    timestamp = now_str()
    
    if notif_type == "departing":
        event_th, event_emoji, grad = "รถกำลังออก", "🚌", "linear-gradient(135deg,#f59e0b,#d97706)"
        subject = f"🚌 รถกำลังออก: {bus_name} (สาย {route})"
    else:
        event_th, event_emoji, grad = "รถออกแล้ว", "🚀", "linear-gradient(135deg,#ef4444,#b91c1c)"
        subject = f"🚀 รถออกแล้ว: {bus_name} (สาย {route})"

    for email in recipients:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = EMAIL_SENDER
        msg["To"]      = email

        html_body = f"""
        <html>
        <body style="font-family: 'Segoe UI', sans-serif; background:#f5f7fa; padding:20px;">
          <div style="background:#fff; border-radius:12px; max-width:500px; margin:auto; overflow:hidden; box-shadow:0 4px 15px rgba(0,0,0,0.1);">
            <div style="background:{grad}; color:#fff; padding:25px; text-align:center;">
              <h1 style="margin:0;">{event_emoji} {event_th}</h1>
              <p style="margin:5px 0 0; opacity:0.8;">{timestamp}</p>
            </div>
            <div style="padding:25px; color:#333;">
              <p><b>รถ:</b> {bus_name} ({label})</p>
              <p><b>สาย:</b> {route} | <b>ที่นั่งว่าง:</b> {seats}</p>
              <p><b>สถานะ:</b> {status}</p>
              <a href="{maps_link}" style="display:block; text-align:center; background:#1a73e8; color:#fff; padding:12px; border-radius:8px; text-decoration:none; font-weight:bold; margin-top:20px;">📍 ดูตำแหน่งใน Google Maps</a>
            </div>
          </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
                server.starttls()
                server.login(EMAIL_SENDER, EMAIL_PASSWORD)
                server.sendmail(EMAIL_SENDER, email, msg.as_bytes())
            print(f"[{now_str()}] ✉️ ส่งแจ้งเตือนสำเร็จ → {email}")
        except Exception as e:
            print(f"[{now_str()}] ❌ ส่งหา {email} ล้มเหลว: {e}")

    # บันทึกข้อมูลลงฐานข้อมูลหลังจากส่งเมลเพื่อให้หน้าเว็บดึงไปโชว์ประวัติในช่อง 'แจ้งเตือน'
    msg_history = "กำลังออกจากสถานี" if notif_type == "departing" else "ออกรถแล้ว"
    save_notification_to_db(bus_name, msg_history)

# ─────────────────────────────────────────────
# DEPARTURE DETECTION LOGIC
# ─────────────────────────────────────────────
def check_and_notify(entity_id: str):
    send_departing = False
    send_departed  = False
    email_args     = {}

    with state_lock:
        entity = bus_state.get(entity_id)
        if not entity: return

        def gv(sec, key): return entity.get(sec, {}).get(key, {}).get("value")
        
        try: speed = float(gv("TIME_SERIES", "speed") or 0)
        except: speed = 0.0

        name   = gv("ENTITY_FIELD", "name") or entity_id
        label  = gv("ENTITY_FIELD", "label") or "-"
        lat    = gv("TIME_SERIES", "latitude")
        lon    = gv("TIME_SERIES", "longitude")
        route  = gv("TIME_SERIES", "route") or gv("TIME_SERIES", "Label") or "-"
        seats  = gv("TIME_SERIES", "availableSeats") or "-"
        status = gv("TIME_SERIES", "status") or "-"

        now     = time.time()
        tracker = departure_tracker.setdefault(entity_id, {
            "first_stop_ts": None, "stop_confirmed": False, "departure_ts": None,
            "notified_departing_at": None, "notified_departed_at": None
        })

        if speed == 0:
            tracker["departure_ts"] = None
            if tracker["first_stop_ts"] is None:
                tracker["first_stop_ts"] = now
            if not tracker["stop_confirmed"] and (now - tracker["first_stop_ts"]) >= STOP_CONFIRM_SECONDS:
                tracker["stop_confirmed"] = True
            return

        if not tracker["stop_confirmed"]:
            tracker["first_stop_ts"] = None
            return

        if tracker["departure_ts"] is None: tracker["departure_ts"] = now
        moving_for = now - tracker["departure_ts"]

        if moving_for < DEPART_CONFIRM_SECONDS:
            last = tracker["notified_departing_at"]
            if not last or (now - last) >= NOTIFY_COOLDOWN_SECONDS:
                tracker["notified_departing_at"] = now
                send_departing = True

        if moving_for >= DEPART_CONFIRM_SECONDS:
            last = tracker["notified_departed_at"]
            if not last or (now - last) >= NOTIFY_COOLDOWN_SECONDS:
                tracker["notified_departed_at"] = now
                tracker.update({"first_stop_ts": None, "stop_confirmed": False, "departure_ts": None})
                send_departed = True

        email_args = dict(bus_name=name, label=label, lat=float(lat or 0), lon=float(lon or 0),
                          route=route, seats=str(seats), status=status)

    if send_departing:
        threading.Thread(target=send_email_to_subscribers, kwargs={**email_args, "notif_type": "departing"}, daemon=True).start()
    if send_departed:
        threading.Thread(target=send_email_to_subscribers, kwargs={**email_args, "notif_type": "departed"}, daemon=True).start()

# ─────────────────────────────────────────────
# CORE: WebSocket & Main
# ─────────────────────────────────────────────
def fetch_new_token():
    try:
        r = requests.post(f"{BASE_URL}/api/auth/login/public", json={"publicId": PUBLIC_ID}, timeout=15)
        r.raise_for_status()
        token = r.json()["token"]
        token_info["token"], token_info["exp"] = token, decode_jwt_exp(token)
        print(f"[{now_str()}] 🔑 Token Refreshed")
    except Exception as e: print(f"Token Error: {e}")

def on_message(ws, message):
    msg = json.loads(message)
    data = msg.get("data", {}).get("data", []) if msg.get("data") else msg.get("update", [])
    for item in data:
        eid = item["entityId"]["id"]
        with state_lock:
            bus_state.setdefault(eid, {"ENTITY_FIELD":{}, "TIME_SERIES":{}})
            latest = item.get("latest", {})
            if "ENTITY_FIELD" in latest: bus_state[eid]["ENTITY_FIELD"].update(latest["ENTITY_FIELD"])
            if "TIME_SERIES" in latest: bus_state[eid]["TIME_SERIES"].update(latest["TIME_SERIES"])
        check_and_notify(eid)

def on_open(ws):
    print(f"[{now_str()}] 🌐 WebSocket Connected")
    ws.send(json.dumps({"authCmd": {"cmdId": 0, "token": token_info["token"]}}))
    keys = [{"type": "TIME_SERIES", "key": k} for k in ["latitude", "longitude", "speed", "status", "route", "Label", "availableSeats"]]
    sub_payload = {"cmds": [{"type": "ENTITY_DATA", "cmdId": 1, "query": {"entityFilter": {"type": "deviceType", "deviceTypes": ["bus"]}, "pageLink": {"pageSize": 100}, "entityFields": [{"type": "ENTITY_FIELD", "key": "name"}, {"type": "ENTITY_FIELD", "key": "label"}], "latestValues": keys}, "latestCmd": {"keys": keys}}]}
    ws.send(json.dumps(sub_payload))

def run_forever():
    while True:
        try:
            if not token_info["token"] or time.time() >= (token_info["exp"] - TOKEN_REFRESH_MARGIN): fetch_new_token()
            global ws_app
            ws_app = websocket.WebSocketApp(WS_URL, header={"Origin": BASE_URL}, on_open=on_open, on_message=on_message)
            ws_app.run_forever(ping_interval=PING_INTERVAL, ping_timeout=PING_TIMEOUT)
        except Exception as e:
            print(f"[{now_str()}] 🔄 Reconnecting... ({e})")
            time.sleep(3)

if __name__ == "__main__":
    run_forever()