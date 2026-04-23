"""
Bus Stop Email Notifier — Flask Backend
=======================================
รัน: python server.py
API Port: 5000

Endpoints:
  POST /api/register       — สมัครสมาชิก {email, password, name}
  POST /api/login          — เข้าสู่ระบบ {email, password} → {token, user}
  GET  /api/me             — ข้อมูล user (ต้องใส่ Authorization: Bearer <token>)
  POST /api/logout         — ออกจากระบบ
  GET  /api/buses          — สถานะรถทั้งหมดปัจจุบัน
  GET  /api/notifications  — ประวัติการแจ้งเตือนของ user นี้
  POST /api/subscribe      — เปิด/ปิดรับแจ้งเตือน {active: true/false}
"""

import threading
import time
import json
import smtplib
import sqlite3
import secrets
import hashlib
import os
import re
import requests
import websocket
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import Flask, request, jsonify
from flask_cors import CORS

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
BASE_URL   = "http://203.158.3.33:8080"
WS_URL     = "ws://203.158.3.33:8080/api/ws"
PUBLIC_ID  = "44a00910-fa93-11ef-94ed-973314b03447"

SMTP_HOST      = "smtp.gmail.com"
SMTP_PORT      = 587
EMAIL_SENDER   = "poommin.tk@gmail.com"
EMAIL_PASSWORD = "uvta yuyz ylah ovws"

STOP_CONFIRM_SECONDS   = 10   # วินาทีที่ต้องจอดต่อเนื่องก่อนถือว่าจอด
NOTIFY_COOLDOWN_SECONDS = 180  # cooldown ต่อ user ต่อรถ (3 นาที)

TOKEN_REFRESH_MARGIN = 60
PING_INTERVAL = 20
PING_TIMEOUT  = 10

DB_PATH = "bus_notifier.db"

# ─────────────────────────────────────────────
# FLASK APP
# ─────────────────────────────────────────────
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT    NOT NULL,
            email      TEXT    UNIQUE NOT NULL,
            password   TEXT    NOT NULL,
            active     INTEGER DEFAULT 1,
            created_at TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token      TEXT PRIMARY KEY,
            user_id    INTEGER NOT NULL,
            expires_at TEXT    NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            bus_name   TEXT,
            route      TEXT,
            lat        REAL,
            lon        REAL,
            status     TEXT,
            seats      TEXT,
            sent_at    TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS user_bus_cooldown (
            user_id    INTEGER NOT NULL,
            bus_id     TEXT    NOT NULL,
            last_sent  TEXT    NOT NULL,
            PRIMARY KEY(user_id, bus_id)
        );
        """)
    print("[DB] Database initialized")

# ─────────────────────────────────────────────
# AUTH HELPERS
# ─────────────────────────────────────────────
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def create_token() -> str:
    return secrets.token_hex(32)

def get_user_from_token(token: str):
    if not token:
        return None
    with get_db() as conn:
        row = conn.execute(
            "SELECT u.* FROM users u JOIN sessions s ON u.id=s.user_id "
            "WHERE s.token=? AND s.expires_at > datetime('now')",
            (token,)
        ).fetchone()
    return dict(row) if row else None

def require_auth():
    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "").strip()
    user = get_user_from_token(token)
    if not user:
        return None, jsonify({"error": "Unauthorized"}), 401
    return user, None, None

# ─────────────────────────────────────────────
# API ROUTES
# ─────────────────────────────────────────────
@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    name     = (data.get("name") or "").strip()
    email    = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()

    if not name or not email or not password:
        return jsonify({"error": "กรุณากรอกข้อมูลให้ครบ"}), 400
    if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        return jsonify({"error": "รูปแบบอีเมลไม่ถูกต้อง"}), 400
    if len(password) < 6:
        return jsonify({"error": "รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร"}), 400

    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO users (name, email, password) VALUES (?,?,?)",
                (name, email, hash_password(password))
            )
        return jsonify({"message": "สมัครสมาชิกสำเร็จ"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "อีเมลนี้ถูกใช้งานแล้ว"}), 409

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email    = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()

    with get_db() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE email=? AND password=?",
            (email, hash_password(password))
        ).fetchone()

    if not user:
        return jsonify({"error": "อีเมลหรือรหัสผ่านไม่ถูกต้อง"}), 401

    token   = create_token()
    expires = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?,?,?)",
            (token, user["id"], expires)
        )

    return jsonify({
        "token": token,
        "user": {
            "id":     user["id"],
            "name":   user["name"],
            "email":  user["email"],
            "active": bool(user["active"]),
        }
    })

@app.route("/api/logout", methods=["POST"])
def logout():
    auth  = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "").strip()
    if token:
        with get_db() as conn:
            conn.execute("DELETE FROM sessions WHERE token=?", (token,))
    return jsonify({"message": "ออกจากระบบแล้ว"})

@app.route("/api/me", methods=["GET"])
def me():
    user, err, code = require_auth()
    if err:
        return err, code
    return jsonify({
        "id":     user["id"],
        "name":   user["name"],
        "email":  user["email"],
        "active": bool(user["active"]),
    })

@app.route("/api/subscribe", methods=["POST"])
def subscribe():
    user, err, code = require_auth()
    if err:
        return err, code
    data   = request.get_json() or {}
    active = bool(data.get("active", True))
    with get_db() as conn:
        conn.execute("UPDATE users SET active=? WHERE id=?", (1 if active else 0, user["id"]))
    status = "เปิด" if active else "ปิด"
    return jsonify({"message": f"{status}การแจ้งเตือนแล้ว", "active": active})

@app.route("/api/buses", methods=["GET"])
def get_buses():
    with state_lock:
        result = []
        for eid, entity in bus_state.items():
            def gv(sec, key):
                return entity.get(sec, {}).get(key, {}).get("value")
            result.append({
                "id":     eid,
                "name":   gv("ENTITY_FIELD", "name"),
                "label":  gv("ENTITY_FIELD", "label"),
                "lat":    gv("TIME_SERIES",  "latitude"),
                "lon":    gv("TIME_SERIES",  "longitude"),
                "speed":  gv("TIME_SERIES",  "speed"),
                "status": gv("TIME_SERIES",  "status"),
                "route":  gv("TIME_SERIES",  "route") or gv("TIME_SERIES", "Label"),
                "seats":  gv("TIME_SERIES",  "availableSeats"),
                "updated_at": entity.get("updated_at"),
            })
    return jsonify(result)

@app.route("/api/notifications", methods=["GET"])
def get_notifications():
    user, err, code = require_auth()
    if err:
        return err, code
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM notifications WHERE user_id=? ORDER BY sent_at DESC LIMIT 50",
            (user["id"],)
        ).fetchall()
    return jsonify([dict(r) for r in rows])

# ─────────────────────────────────────────────
# BUS WEBSOCKET STATE
# ─────────────────────────────────────────────
bus_state    = {}
stop_tracker = {}   # bus_id → {first_stop_ts, last_status}
state_lock   = threading.Lock()

token_info = {"token": None, "exp": 0}
ws_app = None


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def decode_jwt_exp(token: str) -> int:
    import base64
    parts = token.split(".")
    if len(parts) != 3:
        return 0
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    return int(json.loads(base64.urlsafe_b64decode(payload)).get("exp", 0))


def fetch_new_token():
    r = requests.post(f"{BASE_URL}/api/auth/login/public",
                      json={"publicId": PUBLIC_ID}, timeout=15)
    r.raise_for_status()
    token = r.json()["token"]
    token_info["token"] = token
    token_info["exp"]   = decode_jwt_exp(token)
    print(f"[{now_str()}] 🔑 Bus API token refreshed")


def ensure_token():
    if not token_info["token"] or time.time() >= (token_info["exp"] - TOKEN_REFRESH_MARGIN):
        fetch_new_token()

# ─────────────────────────────────────────────
# EMAIL
# ─────────────────────────────────────────────
def send_email(to_email: str, to_name: str, bus_name: str, route: str,
               lat: str, lon: str, status: str, seats: str):
    maps_link = f"https://www.google.com/maps?q={lat},{lon}"
    timestamp = now_str()
    subject   = f"🚌 รถเมล์จอด: {bus_name} (สาย {route})"

    html = f"""<!DOCTYPE html>
<html lang="th"><head><meta charset="UTF-8">
<style>
  body{{font-family:'Sarabun',Arial,sans-serif;background:#0f1923;margin:0;padding:30px}}
  .wrap{{max-width:520px;margin:auto}}
  .card{{background:#1a2535;border-radius:16px;overflow:hidden;
         box-shadow:0 8px 40px rgba(0,0,0,.5)}}
  .top{{background:linear-gradient(135deg,#f97316,#ef4444);padding:32px;color:#fff}}
  .top h1{{margin:0 0 4px;font-size:24px;font-weight:700}}
  .top p{{margin:0;opacity:.85;font-size:13px}}
  .body{{padding:28px 32px}}
  .row{{display:flex;justify-content:space-between;align-items:center;
        padding:12px 0;border-bottom:1px solid #263040}}
  .row:last-child{{border-bottom:none}}
  .lbl{{color:#8899aa;font-size:13px}}
  .val{{color:#e8f0ff;font-weight:600;font-size:14px}}
  .badge{{background:#f9731620;color:#f97316;border:1px solid #f9731650;
          border-radius:20px;padding:3px 14px;font-size:13px}}
  .btn{{display:block;text-align:center;background:linear-gradient(135deg,#f97316,#ef4444);
        color:#fff;padding:16px;border-radius:10px;text-decoration:none;
        font-weight:700;margin-top:24px;font-size:15px;letter-spacing:.5px}}
  .foot{{text-align:center;color:#445566;font-size:11px;padding:16px}}
  .hi{{color:#f97316;font-weight:700}}
</style></head>
<body><div class="wrap"><div class="card">
  <div class="top">
    <h1>รถเมล์จอดที่ป้าย!</h1>
    <p>{timestamp}</p>
  </div>
  <div class="body">
    <p style="color:#8899aa;font-size:14px;margin-top:0">สวัสดี <span class="hi">{to_name}</span> — มีรถเมล์จอดที่ป้ายแล้วครับ</p>
    <div class="row"><span class="lbl">ชื่อรถ</span><span class="val">{bus_name}</span></div>
    <div class="row"><span class="lbl">สายรถ</span><span class="val"><span class="badge">{route}</span></span></div>
    <div class="row"><span class="lbl">สถานะ</span><span class="val">{status}</span></div>
    <div class="row"><span class="lbl">ที่นั่งว่าง</span><span class="val">{seats} ที่นั่ง</span></div>
    <div class="row"><span class="lbl">ละติจูด</span><span class="val">{lat}</span></div>
    <div class="row"><span class="lbl">ลองติจูด</span><span class="val">{lon}</span></div>
    <a href="{maps_link}" class="btn">📍 เปิดตำแหน่งใน Google Maps</a>
  </div>
  <div class="foot">ระบบแจ้งเตือนรถเมล์อัตโนมัติ · ยกเลิกได้ที่ Settings ในแอป</div>
</div></div></body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Bus Notifier <{EMAIL_SENDER}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(f"รถ {bus_name} สาย {route} จอดแล้ว — {maps_link}", "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            s.ehlo(); s.starttls(); s.login(EMAIL_SENDER, EMAIL_PASSWORD)
            s.sendmail(EMAIL_SENDER, to_email, msg.as_bytes())
        print(f"[{now_str()}] Email sent → {to_email} ({bus_name})")
        return True
    except Exception as e:
        print(f"[{now_str()}] Email error: {e}")
        return False

# ─────────────────────────────────────────────
# STOP DETECTION + NOTIFY ALL ACTIVE USERS
# ─────────────────────────────────────────────
def notify_all_users(bus_id, bus_name, route, lat, lon, status, seats):
    """ส่งอีเมลให้ users ที่ active=True ทุกคน (ที่ยังไม่ใน cooldown)"""
    with get_db() as conn:
        users = conn.execute(
            "SELECT id, name, email FROM users WHERE active=1"
        ).fetchall()

    now_dt = datetime.now()
    now_iso = now_dt.strftime("%Y-%m-%d %H:%M:%S")

    for user in users:
        uid = user["id"]
        with get_db() as conn:
            last = conn.execute(
                "SELECT last_sent FROM user_bus_cooldown WHERE user_id=? AND bus_id=?",
                (uid, bus_id)
            ).fetchone()

        if last:
            delta = (now_dt - datetime.fromisoformat(last["last_sent"])).total_seconds()
            if delta < NOTIFY_COOLDOWN_SECONDS:
                continue  # ยังอยู่ใน cooldown

        ok = send_email(user["email"], user["name"], bus_name, route,
                        str(lat), str(lon), status, str(seats))
        if ok:
            with get_db() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO user_bus_cooldown VALUES (?,?,?)",
                    (uid, bus_id, now_iso)
                )
                conn.execute(
                    "INSERT INTO notifications (user_id,bus_name,route,lat,lon,status,seats)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (uid, bus_name, route, lat, lon, status, seats)
                )


def check_and_notify(entity_id: str):
    with state_lock:
        entity = bus_state.get(entity_id)
        if not entity:
            return

        def gv(sec, key):
            return entity.get(sec, {}).get(key, {}).get("value")

        status = (gv("TIME_SERIES", "status") or "").lower()
        name   = gv("ENTITY_FIELD", "name")  or entity_id
        label  = gv("ENTITY_FIELD", "label") or "-"
        lat    = gv("TIME_SERIES",  "latitude")  or 0
        lon    = gv("TIME_SERIES",  "longitude") or 0
        route  = gv("TIME_SERIES",  "route") or gv("TIME_SERIES", "Label") or "-"
        seats  = gv("TIME_SERIES",  "availableSeats") or "-"

        is_stopped = any(s in status for s in ("stop", "idle", "จอด"))
        now = time.time()

        tracker = stop_tracker.setdefault(entity_id, {
            "first_stop_ts": None,
            "last_status":   "",
        })

        if not is_stopped:
            tracker["first_stop_ts"] = None
            tracker["last_status"]   = status
            return

        if tracker["first_stop_ts"] is None:
            tracker["first_stop_ts"] = now
            print(f"[{now_str()}] ⏸  {name} status={status} เริ่มนับ...")
            return

        if (now - tracker["first_stop_ts"]) < STOP_CONFIRM_SECONDS:
            return

        # ยืนยันว่าจอดจริง — ส่ง thread แยก
        tracker["first_stop_ts"] = None   # reset เพื่อไม่ spam

    threading.Thread(
        target=notify_all_users,
        args=(entity_id, name, route, lat, lon, status, seats),
        daemon=True,
    ).start()
    print(f"[{now_str()}] {name} จอด (status={status}) — กำลังแจ้งเตือน users...")


# ─────────────────────────────────────────────
# WEBSOCKET
# ─────────────────────────────────────────────
def build_subscribe_payload():
    keys = [
        {"type": "ATTRIBUTE",   "key": "perimeter"},
        {"type": "TIME_SERIES", "key": "latitude"},
        {"type": "TIME_SERIES", "key": "longitude"},
        {"type": "TIME_SERIES", "key": "speed"},
        {"type": "TIME_SERIES", "key": "status"},
        {"type": "TIME_SERIES", "key": "route"},
        {"type": "TIME_SERIES", "key": "Label"},
        {"type": "TIME_SERIES", "key": "availableSeats"},
        {"type": "TIME_SERIES", "key": "peopleIn"},
        {"type": "TIME_SERIES", "key": "peopleOut"},
    ]
    return {"cmds": [{"type": "ENTITY_DATA", "cmdId": 1, "query": {
        "entityFilter": {
            "type": "deviceType", "resolveMultiple": True,
            "deviceTypes": ["bus"], "deviceNameFilter": ""
        },
        "pageLink": {"page": 0, "pageSize": 16384, "textSearch": None, "dynamic": True},
        "entityFields": [
            {"type": "ENTITY_FIELD", "key": "name"},
            {"type": "ENTITY_FIELD", "key": "label"},
            {"type": "ENTITY_FIELD", "key": "additionalInfo"},
        ],
        "latestValues": keys,
    }, "latestCmd": {"keys": keys}}]}


def merge_entity(item: dict):
    eid = item["entityId"]["id"]
    with state_lock:
        if eid not in bus_state:
            bus_state[eid] = {"entityId": item["entityId"],
                              "ENTITY_FIELD": {}, "ATTRIBUTE": {},
                              "TIME_SERIES": {}, "updated_at": None}
        for sec in ("ENTITY_FIELD", "ATTRIBUTE", "TIME_SERIES"):
            if sec in item.get("latest", {}):
                bus_state[eid].setdefault(sec, {}).update(item["latest"][sec])
        bus_state[eid]["updated_at"] = now_str()


def on_open(ws):
    print(f"[{now_str()}] WebSocket connected")
    ensure_token()
    ws.send(json.dumps({"authCmd": {"cmdId": 0, "token": token_info["token"]}}))
    ws.send(json.dumps(build_subscribe_payload()))


def on_message(ws, message):
    try:
        msg = json.loads(message)
    except Exception:
        return

    if msg.get("errorCode", 0) != 0:
        print(f"[{now_str()}] WS error: {msg.get('errorMsg')}")
        return

    if msg.get("data") and msg["data"].get("data"):
        for item in msg["data"]["data"]:
            merge_entity(item)
            check_and_notify(item["entityId"]["id"])
        print(f"[{now_str()}] Snapshot: {len(msg['data']['data'])} buses")

    if msg.get("update"):
        for item in msg["update"]:
            merge_entity(item)
            check_and_notify(item["entityId"]["id"])


def on_error(ws, error):
    print(f"[{now_str()}] ⚠ WS error: {error}")


def on_close(ws, code, msg):
    print(f"[{now_str()}] WS closed: {code}")


def ws_loop():
    global ws_app
    while True:
        try:
            ensure_token()
            ws_app = websocket.WebSocketApp(
                WS_URL, header={"Origin": BASE_URL},
                on_open=on_open, on_message=on_message,
                on_error=on_error, on_close=on_close,
            )
            ws_app.run_forever(ping_interval=PING_INTERVAL, ping_timeout=PING_TIMEOUT)
        except Exception as e:
            print(f"[{now_str()}] WS loop error: {e}")
        print(f"[{now_str()}] Reconnecting in 3s...")
        time.sleep(3)


def token_watcher():
    global ws_app
    while True:
        time.sleep(5)
        try:
            if not token_info["token"] or time.time() >= (token_info["exp"] - TOKEN_REFRESH_MARGIN):
                fetch_new_token()
                if ws_app:
                    ws_app.close()
        except Exception as e:
            print(f"[{now_str()}] Token watcher error: {e}")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    threading.Thread(target=token_watcher, daemon=True).start()
    threading.Thread(target=ws_loop, daemon=True).start()
    
    port_number = 5001
    
    print("=" * 55)
    print("  Bus Notifier Server  |  http://localhost:{port_number}")
    print("=" * 55)
    app.run(host="0.0.0.0", port=port_number, debug=False)