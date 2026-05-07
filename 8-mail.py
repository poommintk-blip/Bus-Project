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
SMTP_HOST        = "smtp.gmail.com"
SMTP_PORT        = 587
EMAIL_SENDER     = "poommin.tk@gmail.com"
EMAIL_PASSWORD   = "uvta yuyz ylah ovws"
EMAIL_RECIPIENTS = ["poommin.tk@gmail.com"]

# ─── TIMING CONFIG ───────────────────────────────────────────────────────────
# รถถือว่า "จอดยืนยัน" เมื่อ speed = 0 ติดต่อกัน STOP_CONFIRM_SECONDS วินาที
STOP_CONFIRM_SECONDS = 10

# รถถือว่า "ออกแล้ว" เมื่อ speed > 0 ติดต่อกัน DEPART_CONFIRM_SECONDS วินาที
DEPART_CONFIRM_SECONDS = 10

# ไม่ส่งซ้ำภายใน N วินาที (ต่อคัน ต่อ event) หลังส่งแล้ว
NOTIFY_COOLDOWN_SECONDS = 360
# ─────────────────────────────────────────────────────────────────────────────

TOKEN_REFRESH_MARGIN = 60
PING_INTERVAL = 20
PING_TIMEOUT  = 10

bus_state        = {}   # entity_id → entity dict
departure_tracker = {}  # entity_id → tracker dict  ← เปลี่ยนชื่อ + โครงสร้างใหม่
state_lock       = threading.Lock()

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
    return int(json.loads(decoded.decode()).get("exp", 0))


def haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi    = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
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
# EMAIL NOTIFICATION  (รองรับ 2 ประเภท)
# notif_type: "departing" = กำลังออก, "departed" = ออกแล้ว
# ─────────────────────────────────────────────
def send_email_notification(bus_name: str, label: str, lat: float, lon: float,
                             route: str, seats: str, status: str,
                             notif_type: str = "departing"):

    maps_link = f"https://www.google.com/maps?q={lat},{lon}"
    timestamp = now_str()

    if notif_type == "departing":
        event_th    = "รถกำลังออก"
        event_emoji = "🚌"
        header_grad = "linear-gradient(135deg,#f59e0b,#d97706)"   # สีส้ม
        subject     = f"🚌 รถกำลังออก: {bus_name} (สาย {route})"
    else:  # departed
        event_th    = "รถออกแล้ว"
        event_emoji = "🚀"
        header_grad = "linear-gradient(135deg,#ef4444,#b91c1c)"   # สีแดง
        subject     = f"🚀 รถออกแล้ว: {bus_name} (สาย {route})"

    html_body = f"""
<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background:#f5f7fa; margin:0; padding:20px; }}
    .card {{ background:#fff; border-radius:12px; max-width:520px; margin:auto;
             box-shadow:0 4px 20px rgba(0,0,0,.10); overflow:hidden; }}
    .header {{ background:{header_grad}; color:#fff; padding:28px 32px; }}
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
      <h1>{event_emoji} {event_th}</h1>
      <p>{timestamp}</p>
    </div>
    <div class="body">
      <div class="row">
        <span class="label">ชื่อรถ</span>
        <span class="value">{bus_name}</span>
      </div>
      <div class="row">
        <span class="label">ป้ายทะเบียน / Label</span>
        <span class="value">{label}</span>
      </div>
      <div class="row">
        <span class="label">สายรถ (Route)</span>
        <span class="value"><span class="badge">{route}</span></span>
      </div>
      <div class="row">
        <span class="label">สถานะ</span>
        <span class="value">{status}</span>
      </div>
      <div class="row">
        <span class="label">ที่นั่งว่าง</span>
        <span class="value">{seats} ที่นั่ง</span>
      </div>
      <div class="row">
        <span class="label">ละติจูด (Latitude)</span>
        <span class="value">{lat}</span>
      </div>
      <div class="row">
        <span class="label">ลองติจูด (Longitude)</span>
        <span class="value">{lon}</span>
      </div>
      <a href="{maps_link}" class="btn">📍 ดูตำแหน่งใน Google Maps</a>
    </div>
    <div class="footer">ระบบแจ้งเตือนรถเมล์อัตโนมัติ</div>
  </div>
</body>
</html>
"""

    plain_body = (
        f"{event_th}: {bus_name} (สาย {route})\n"
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
        print(f"[{now_str()}] ✉️  [{event_th}] ส่งแล้ว → {EMAIL_RECIPIENTS} (รถ: {bus_name})")
    except Exception as e:
        print(f"[{now_str()}] ส่งอีเมลไม่ได้: {e}")


# ─────────────────────────────────────────────
# DEPARTURE DETECTION LOGIC  ← เปลี่ยนใหม่ทั้งหมด
# ─────────────────────────────────────────────
def _new_tracker() -> dict:
    return {
        "first_stop_ts":         None,   # timestamp ที่ speed เริ่มเป็น 0
        "stop_confirmed":        False,  # True เมื่อจอดยืนยัน >= STOP_CONFIRM_SECONDS
        "departure_ts":          None,   # timestamp ที่ speed เริ่ม > 0 หลังจอดยืนยัน
        "notified_departing_at": None,   # ส่ง "กำลังออก" ครั้งล่าสุด
        "notified_departed_at":  None,   # ส่ง "ออกแล้ว" ครั้งล่าสุด
    }


def check_and_notify(entity_id: str):
    """
    State machine:
      IDLE → STOPPING (speed==0) → STOP_CONFIRMED → DEPARTING (speed>0) → DEPARTED
    แต่ละ transition ที่ต้องแจ้งเตือน:
      DEPARTING  → ส่ง email "กำลังออก"  (ทันทีที่ speed > 0 หลังจอดยืนยัน)
      DEPARTED   → ส่ง email "ออกแล้ว"   (หลังวิ่งต่อเนื่อง DEPART_CONFIRM_SECONDS)
    """
    # ── รวบรวมข้อมูลและตัดสินใจภายใน lock ────────────────────────────────────
    send_departing = False
    send_departed  = False
    email_args     = {}

    with state_lock:
        entity = bus_state.get(entity_id)
        if not entity:
            return

        def gv(sec, key):
            return entity.get(sec, {}).get(key, {}).get("value")

        try:
            speed = float(gv("TIME_SERIES", "speed") or 0)
        except (ValueError, TypeError):
            speed = 0.0

        name   = gv("ENTITY_FIELD", "name")  or entity_id
        label  = gv("ENTITY_FIELD", "label") or "-"
        lat    = gv("TIME_SERIES",  "latitude")
        lon    = gv("TIME_SERIES",  "longitude")
        route  = gv("TIME_SERIES",  "route") or gv("TIME_SERIES", "Label") or "-"
        seats  = gv("TIME_SERIES",  "availableSeats") or "-"
        status = gv("TIME_SERIES",  "status") or "-"
        lat_f  = float(lat) if lat else 0.0
        lon_f  = float(lon) if lon else 0.0

        now     = time.time()
        tracker = departure_tracker.setdefault(entity_id, _new_tracker())

        # ── กรณี: รถหยุด (speed == 0) ──────────────────────────────────────────
        if speed == 0:
            tracker["departure_ts"] = None   # reset การนับการออก

            if tracker["first_stop_ts"] is None:
                tracker["first_stop_ts"] = now
                print(f"[{now_str()}] ⏸  {name} เริ่มจอด... (รอยืนยัน {STOP_CONFIRM_SECONDS}s)")

            stopped_for = now - tracker["first_stop_ts"]
            if not tracker["stop_confirmed"] and stopped_for >= STOP_CONFIRM_SECONDS:
                tracker["stop_confirmed"] = True
                print(f"[{now_str()}] ✅ {name} จอดยืนยันแล้ว ({stopped_for:.0f}s)")
            return

        # ── กรณี: รถวิ่ง (speed > 0) ───────────────────────────────────────────
        if not tracker["stop_confirmed"]:
            # ยังไม่เคยจอดยืนยัน → reset stop tracking แล้วข้าม
            tracker["first_stop_ts"] = None
            return

        # รถวิ่งหลังจากจอดยืนยัน → เริ่มนับการออก
        if tracker["departure_ts"] is None:
            tracker["departure_ts"] = now
            print(f"[{now_str()}] 🚦 {name} เริ่มวิ่ง! (กำลังออก)")

        moving_for = now - tracker["departure_ts"]

        # ── "กำลังออก": ส่งทันที่ departure_ts ถูกตั้ง ────────────────────────
        if moving_for < DEPART_CONFIRM_SECONDS:
            last = tracker["notified_departing_at"]
            if not last or (now - last) >= NOTIFY_COOLDOWN_SECONDS:
                tracker["notified_departing_at"] = now
                send_departing = True

        # ── "ออกแล้ว": ส่งหลังวิ่งต่อเนื่อง DEPART_CONFIRM_SECONDS ──────────
        if moving_for >= DEPART_CONFIRM_SECONDS:
            last = tracker["notified_departed_at"]
            if not last or (now - last) >= NOTIFY_COOLDOWN_SECONDS:
                tracker["notified_departed_at"] = now
                # reset ทั้งหมด เพื่อรับรอบถัดไป
                tracker["first_stop_ts"]  = None
                tracker["stop_confirmed"] = False
                tracker["departure_ts"]   = None
                send_departed = True

        email_args = dict(bus_name=name, label=label, lat=lat_f, lon=lon_f,
                          route=route, seats=str(seats), status=status)

    # ── ส่งอีเมลนอก lock ───────────────────────────────────────────────────────
    if send_departing:
        print(f"[{now_str()}] 🚌 {email_args['bus_name']} กำลังออก! กำลังส่งอีเมล...")
        threading.Thread(
            target=send_email_notification,
            kwargs={**email_args, "notif_type": "departing"},
            daemon=True,
        ).start()

    if send_departed:
        print(f"[{now_str()}] 🚀 {email_args['bus_name']} ออกแล้ว! กำลังส่งอีเมล...")
        threading.Thread(
            target=send_email_notification,
            kwargs={**email_args, "notif_type": "departed"},
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
                "entityId":     item["entityId"],
                "ENTITY_FIELD": {},
                "ATTRIBUTE":    {},
                "TIME_SERIES":  {},
                "updated_at":   None,
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
            name   = get_value(entity, "ENTITY_FIELD", "name")       or "-"
            label  = get_value(entity, "ENTITY_FIELD", "label")      or "-"
            lat    = get_value(entity, "TIME_SERIES",  "latitude")   or "-"
            lon    = get_value(entity, "TIME_SERIES",  "longitude")  or "-"
            speed  = get_value(entity, "TIME_SERIES",  "speed")      or "-"
            status = get_value(entity, "TIME_SERIES",  "status")     or "-"
            seats  = get_value(entity, "TIME_SERIES",  "availableSeats") or "-"

            # แสดงสถานะการออกจาก tracker
            tr = departure_tracker.get(eid, {})
            if tr.get("departure_ts"):
                dep_state = "กำลังออก 🚌"
            elif tr.get("stop_confirmed"):
                dep_state = "จอดยืนยัน ✅"
            elif tr.get("first_stop_ts"):
                dep_state = "กำลังจอด ⏸"
            else:
                dep_state = "วิ่ง 🟢" if speed not in ("-", "0", 0) else "-"

            rows.append({"name": name, "label": label, "lat": lat, "lon": lon,
                         "speed": speed, "status": status, "seats": seats,
                         "dep_state": dep_state})
        rows.sort(key=lambda x: x["name"])

    os.system("cls" if os.name == "nt" else "clear")
    print(f"[{now_str()}]  รถทั้งหมด: {len(rows)} คัน  |  Email → {EMAIL_RECIPIENTS}")
    print("-" * 125)
    print(f"{'NAME':25} {'LABEL':8} {'LAT':12} {'LON':12} {'SPEED':8} {'STATUS':18} {'SEATS':6} {'STATE':18}")
    print("-" * 125)
    for r in rows:
        print(f"{str(r['name'])[:25]:25} {str(r['label'])[:8]:8} "
              f"{str(r['lat'])[:12]:12} {str(r['lon'])[:12]:12} "
              f"{str(r['speed'])[:8]:8} {str(r['status'])[:18]:18} "
              f"{str(r['seats'])[:6]:6} {str(r['dep_state'])[:18]:18}")
    print("-" * 125)


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

    if msg.get("data") and msg["data"].get("data"):
        for item in msg["data"]["data"]:
            merge_entity(item)
            check_and_notify(item["entityId"]["id"])
        print(f"[{now_str()}] Snapshot: {len(msg['data']['data'])} entities")
        print_bus_table()

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
    print("   Bus Departure Email Notifier")
    print(f"   Sending to: {EMAIL_RECIPIENTS}")
    print(f"   Stop confirm : {STOP_CONFIRM_SECONDS}s")
    print(f"   Depart confirm: {DEPART_CONFIRM_SECONDS}s")
    print(f"   Cooldown      : {NOTIFY_COOLDOWN_SECONDS}s")
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