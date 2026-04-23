import requests
import websocket
import json
import time
import threading
import os
import smtplib
import math
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


BASE_URL   = "http://203.158.3.33:8080"
WS_URL     = "ws://203.158.3.33:8080/api/ws"
PUBLIC_ID  = "44a00910-fa93-11ef-94ed-973314b03447"

# Email settings (Gmail App Password)
SMTP_HOST     = "smtp.gmail.com"
SMTP_PORT     = 587
EMAIL_SENDER  = "poommin.tk@gmail.com"          # ← เปลี่ยนเป็นอีเมลของคุณ (ต้องเป็น Gmail และสร้าง App Password แล้ว)
EMAIL_PASSWORD = "uvta yuyz ylah ovws"          # Gmail App Password
#EMAIL_RECIPIENTS = ["poommin.tk@gmail.com"]     # ← เพิ่มอีเมลปลายทางได้ที่นี่
EMAIL_RECIPIENTS = ["sans78r@gmail.com", "poommin.tk@gmail.com", "thitimasakoonram@gmail.com"]  # ตัวอย่างส่งถึงหลายคน


# รถถือว่า "จอด" เมื่อ speed = 0 ติดต่อกัน STOP_CONFIRM_SECONDS วินาที
STOP_CONFIRM_SECONDS = 10

# cooldown: ไม่ส่งซ้ำภายใน N วินาที (ต่อคัน) หลังส่งแล้ว
NOTIFY_COOLDOWN_SECONDS = 120

# ─────────────────────────────────────────────
# INTERNAL STATE
# ─────────────────────────────────────────────
TOKEN_REFRESH_MARGIN = 60
PING_INTERVAL = 20
PING_TIMEOUT  = 10

bus_state      = {}   # entity_id → entity dict
stop_tracker   = {}   # entity_id → {"first_stop_ts": float, "notified_at": float|None}
state_lock     = threading.Lock()

token_info = {"token": None, "exp": 0}
ws_app = None


# ─────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def decode_jwt_exp(token: str) -> int:
    import base64
    parts = token.split(".")
    if len(parts) != 3:
        return 0
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    decoded = base64.urlsafe_b64decode(payload + padding)
    return int(json.loads(decoded.decode())  .get("exp", 0))


# ─────────────────────────────────────────────
# HAVERSINE – คำนวณระยะทาง (เมตร) ระหว่าง 2 จุด GPS
# ─────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2) -> float:
    """Return distance in metres between two GPS coordinates."""
    R = 6_371_000  # Earth radius in metres
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi       = math.radians(lat2 - lat1)
    dlambda    = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ─────────────────────────────────────────────
# TOKEN MANAGEMENT
# ─────────────────────────────────────────────
def fetch_new_token():
    url = f"{BASE_URL}/api/auth/login/public"
    r   = requests.post(url, json={"publicId": PUBLIC_ID}, timeout=15)
    r.raise_for_status()
    token = r.json()["token"]
    exp   = decode_jwt_exp(token)
    token_info["token"] = token
    token_info["exp"]   = exp
    print(f"[{now_str()}] 🔑 token refreshed, exp={datetime.fromtimestamp(exp).strftime('%H:%M:%S')}")


def token_needs_refresh() -> bool:
    return not token_info["token"] or time.time() >= (token_info["exp"] - TOKEN_REFRESH_MARGIN)


def ensure_token():
    if token_needs_refresh():
        fetch_new_token()

# ─────────────────────────────────────────────
# EMAIL NOTIFICATION
# ─────────────────────────────────────────────
def send_email_notification(bus_name: str, label: str, lat: float, lon: float,
                             route: str, seats: str, status: str):
    """ส่งอีเมลแจ้งเตือนเมื่อรถจอด"""
    maps_link = f"https://www.google.com/maps?q={lat},{lon}"
    timestamp = now_str()

    subject = f"รถเมล์จอด: {bus_name} (สาย {route})"

    html_body = f"""
<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background:#f5f7fa; margin:0; padding:20px; }}
    .card {{ background:#fff; border-radius:12px; max-width:520px; margin:auto;
             box-shadow:0 4px 20px rgba(0,0,0,.10); overflow:hidden; }}
    .header {{ background:linear-gradient(135deg,#1a73e8,#0d47a1); color:#fff;
               padding:28px 32px; }}
    .header h1 {{ margin:0 0 6px; font-size:22px; }}
    .header p  {{ margin:0; opacity:.85; font-size:14px; }}
    .body {{ padding:28px 32px; }}
    .row {{ display:flex; justify-content:space-between; padding:10px 0;
            border-bottom:1px solid #eee; font-size:15px; }}
    .row:last-child {{ border-bottom:none; }}
    .label {{ color:#666; }}
    .value {{ font-weight:600; color:#1a1a2e; }}
    .badge {{ display:inline-block; background:#e8f0fe; color:#1a73e8;
              border-radius:20px; padding:2px 12px; font-size:13px; }}
    .btn {{ display:block; text-align:center; background:#1a73e8; color:#fff;
            padding:14px; border-radius:8px; text-decoration:none;
            font-weight:600; margin-top:24px; font-size:15px; }}
    .footer {{ text-align:center; color:#aaa; font-size:12px; padding:16px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <h1>รถเมล์จอดที่ป้าย</h1>
      <p>{timestamp}</p>
    </div>
    <div class="body">
      <div class="row">
        <span class="label">ชื่อรถ\n </span>
        <span class="value">{bus_name}</span>
      </div>
      <div class="row">
        <span class="label">ป้ายทะเบียน / Label\n </span>
        <span class="value">{label}</span>
      </div>
      <div class="row">
        <span class="label">สายรถ (Route)\n </span>
        <span class="value"><span class="badge">{route}</span></span>
      </div>
      <div class="row">
        <span class="label">สถานะ\n </span>
        <span class="value">{status}</span>
      </div>
      <div class="row">
        <span class="label">ที่นั่งว่าง\n </span>
        <span class="value">{seats} ที่นั่ง</span>
      </div>
      <div class="row">
        <span class="label">ละติจูด (Latitude)\n </span>
        <span class="value">{lat}</span>
      </div>
      <div class="row">
        <span class="label">ลองติจูด (Longitude)\n </span>
        <span class="value">{lon}</span>
      </div>
      <a href="{maps_link}" class="btn"> ดูตำแหน่งใน Google Maps </a>
    </div>
    <div class="footer">ระบบแจ้งเตือนรถเมล์อัตโนมัติ</div>
  </div>
</body>
</html>
"""

    plain_body = (
        f"รถเมล์จอด: {bus_name} (สาย {route})\n"
        f"สถานะ: {status}\n"
        f"ที่นั่งว่าง: {seats}\n"
        f"ตำแหน่ง: lat={lat}, lon={lon}\n"
        f"Google Maps: {maps_link}\n"
        f"เวลา: {timestamp}"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = ", ".join(EMAIL_RECIPIENTS)
    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body,  "html",  "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENTS, msg.as_bytes())
        print(f"[{now_str()}] อีเมลส่งแล้ว → {EMAIL_RECIPIENTS} (รถ: {bus_name})")
    except Exception as e:
        print(f"[{now_str()}] ส่งอีเมลไม่ได้: {e}")


# ─────────────────────────────────────────────
# STOP DETECTION LOGIC
# ─────────────────────────────────────────────
def check_and_notify(entity_id: str):
    """เรียกหลัง merge_entity ทุกครั้ง — ตรวจว่ารถจอดหรือยัง"""
    with state_lock:
        entity = bus_state.get(entity_id)
        if not entity:
            return

        # ดึงค่าจาก state
        def gv(sec, key):
            return entity.get(sec, {}).get(key, {}).get("value")

        try:
            speed = float(gv("TIME_SERIES", "speed") or 1)
        except (ValueError, TypeError):
            speed = 1.0

        name   = gv("ENTITY_FIELD", "name")  or entity_id
        label  = gv("ENTITY_FIELD", "label") or "-"
        lat    = gv("TIME_SERIES",  "latitude")
        lon    = gv("TIME_SERIES",  "longitude")
        route  = gv("TIME_SERIES",  "route")  or gv("TIME_SERIES", "Label") or "-"
        seats  = gv("TIME_SERIES",  "availableSeats") or "-"
        status = gv("TIME_SERIES",  "status") or "-"

        is_stopped = (speed == 0)
        now = time.time()

        tracker = stop_tracker.setdefault(entity_id, {
            "first_stop_ts": None,
            "notified_at":   None,
        })

        if not is_stopped:
            # รถวิ่ง → reset
            tracker["first_stop_ts"] = None
            return

        # รถหยุด
        if tracker["first_stop_ts"] is None:
            tracker["first_stop_ts"] = now
            print(f"[{now_str()}] ⏸  {name} เริ่มจอด... (รอยืนยัน {STOP_CONFIRM_SECONDS}s)")
            return

        stopped_for = now - tracker["first_stop_ts"]
        if stopped_for < STOP_CONFIRM_SECONDS:
            return  # ยังไม่ถึงเวลายืนยัน

        # ยืนยันแล้วว่าจอด — ตรวจ cooldown
        last_notified = tracker["notified_at"]
        if last_notified and (now - last_notified) < NOTIFY_COOLDOWN_SECONDS:
            return  # ส่งไปแล้ว ยังอยู่ใน cooldown

        # ส่งแจ้งเตือน!
        tracker["notified_at"] = now
        lat_f = float(lat) if lat else 0.0
        lon_f = float(lon) if lon else 0.0

    # ส่งนอก lock เพื่อไม่บล็อก
    print(f"[{now_str()}] {name} จอดแล้ว! กำลังส่งอีเมล...")
    threading.Thread(
        target=send_email_notification,
        args=(name, label, lat_f, lon_f, route, str(seats), status),
        daemon=True,
    ).start()


# ─────────────────────────────────────────────
# WEBSOCKET HELPERS
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
            "type": "deviceType",
            "resolveMultiple": True,
            "deviceTypes": ["bus"],
            "deviceNameFilter": ""
        },
        "pageLink": {"page": 0, "pageSize": 16384, "textSearch": None, "dynamic": True},
        "entityFields": [
            {"type": "ENTITY_FIELD", "key": "name"},
            {"type": "ENTITY_FIELD", "key": "label"},
            {"type": "ENTITY_FIELD", "key": "additionalInfo"},
        ],
        "latestValues": keys,
    }, "latestCmd": {"keys": keys}}]}


def merge_latest_section(target, source, section):
    if section not in source:
        return
    target.setdefault(section, {}).update(source[section])


def merge_entity(item: dict):
    entity_id = item["entityId"]["id"]
    with state_lock:
        if entity_id not in bus_state:
            bus_state[entity_id] = {
                "entityId":    item["entityId"],
                "ENTITY_FIELD": {},
                "ATTRIBUTE":   {},
                "TIME_SERIES": {},
                "updated_at":  None,
            }
        latest = item.get("latest", {})
        for sec in ("ENTITY_FIELD", "ATTRIBUTE", "TIME_SERIES"):
            merge_latest_section(bus_state[entity_id], latest, sec)
        bus_state[entity_id]["updated_at"] = now_str()


def get_value(entity, section, key):
    return entity.get(section, {}).get(key, {}).get("value")


def print_bus_table():
    with state_lock:
        rows = []
        for eid, entity in bus_state.items():
            name   = get_value(entity, "ENTITY_FIELD", "name")  or "-"
            label  = get_value(entity, "ENTITY_FIELD", "label") or "-"
            lat    = get_value(entity, "TIME_SERIES",  "latitude")  or "-"
            lon    = get_value(entity, "TIME_SERIES",  "longitude") or "-"
            speed  = get_value(entity, "TIME_SERIES",  "speed")     or "-"
            status = get_value(entity, "TIME_SERIES",  "status")    or "-"
            seats  = get_value(entity, "TIME_SERIES",  "availableSeats") or "-"
            rows.append({"name": name, "label": label, "lat": lat, "lon": lon,
                         "speed": speed, "status": status, "seats": seats})
        rows.sort(key=lambda x: x["name"])

    os.system("cls" if os.name == "nt" else "clear")
    print(f"[{now_str()}]  รถทั้งหมด: {len(rows)} คัน  |  Email → {EMAIL_RECIPIENTS}")
    print("-" * 110)
    print(f"{'NAME':25} {'LABEL':8} {'LAT':12} {'LON':12} {'SPEED':8} {'STATUS':18} {'SEATS':6} {'STOPPED?':10}")
    print("-" * 110)
    for r in rows:
        try:
            stopped = "รถจอด" if float(str(r["speed"])) == 0 else "รถวิ่ง"
        except Exception:
            stopped = "-"
        print(f"{str(r['name'])[:25]:25} {str(r['label'])[:8]:8} "
              f"{str(r['lat'])[:12]:12} {str(r['lon'])[:12]:12} "
              f"{str(r['speed'])[:8]:8} {str(r['status'])[:18]:18} "
              f"{str(r['seats'])[:6]:6} {stopped:10}")
    print("-" * 110)


# ─────────────────────────────────────────────
# WEBSOCKET CALLBACKS
# ─────────────────────────────────────────────
def send_auth_and_subscribe(ws):
    ensure_token()
    ws.send(json.dumps({"authCmd": {"cmdId": 0, "token": token_info["token"]}}))
    print(f"[{now_str()}] ✔ auth sent")
    ws.send(json.dumps(build_subscribe_payload()))
    print(f"[{now_str()}] ✔ subscribe sent")


def on_open(ws):
    print(f"[{now_str()}] WebSocket connected")
    send_auth_and_subscribe(ws)


def on_message(ws, message):
    try:
        msg = json.loads(message)
    except Exception as e:
        print(f"[{now_str()}] JSON error: {e}")
        return

    if msg.get("errorCode", 0) != 0:
        print(f"[{now_str()}] Server error: {msg.get('errorMsg')}")
        return

    # Initial snapshot
    if msg.get("data") and msg["data"].get("data"):
        for item in msg["data"]["data"]:
            merge_entity(item)
            check_and_notify(item["entityId"]["id"])
        print(f"[{now_str()}] Snapshot: {len(msg['data']['data'])} entities")
        print_bus_table()

    # Incremental updates
    if msg.get("update"):
        for item in msg["update"]:
            merge_entity(item)
            check_and_notify(item["entityId"]["id"])
        print_bus_table()


def on_error(ws, error):
    print(f"[{now_str()}] WebSocket error: {error}")


def on_close(ws, code, msg):
    print(f"[{now_str()}] WebSocket closed: code={code}")


# ─────────────────────────────────────────────
# TOKEN WATCHER THREAD
# ─────────────────────────────────────────────
def token_refresh_watcher():
    global ws_app
    while True:
        time.sleep(5)
        try:
            if token_needs_refresh():
                print(f"[{now_str()}] Token expiring, reconnecting...")
                fetch_new_token()
                if ws_app:
                    ws_app.close()
        except Exception as e:
            print(f"[{now_str()}] Watcher error: {e}")


# ─────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────
def run_forever():
    global ws_app
    print("=" * 60)
    print("   Bus Stop Email Notifier  ")
    print(f"   Sending to: {EMAIL_RECIPIENTS}")
    print(f"   Stop confirm: {STOP_CONFIRM_SECONDS}s | Cooldown: {NOTIFY_COOLDOWN_SECONDS}s")
    print("=" * 60)

    while True:
        try:
            ensure_token()
            ws_app = websocket.WebSocketApp(
                WS_URL,
                header={"Origin": BASE_URL},
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            ws_app.run_forever(ping_interval=PING_INTERVAL, ping_timeout=PING_TIMEOUT)
        except KeyboardInterrupt:
            print(f"\n[{now_str()}] Stopped by user")
            break
        except Exception as e:
            print(f"[{now_str()}] Loop error: {e}")

        print(f"[{now_str()}] Reconnecting in 3s...")
        time.sleep(3)


if __name__ == "__main__":
    threading.Thread(target=token_refresh_watcher, daemon=True).start()
    run_forever()