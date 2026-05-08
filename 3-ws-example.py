import requests
import websocket
import json
import time
import threading
import os
from datetime import datetime

BASE_URL = "http://203.158.3.33:8080"
WS_URL = "ws://203.158.3.33:8080/api/ws"
PUBLIC_ID = "44a00910-fa93-11ef-94ed-973314b03447"

# refresh token ล่วงหน้าก่อนหมดอายุ
TOKEN_REFRESH_MARGIN = 60  # seconds

# ping websocket เป็นระยะ
PING_INTERVAL = 20
PING_TIMEOUT = 10

# state เก็บข้อมูลรถทุกคัน
bus_state = {}
state_lock = threading.Lock()

# token state
token_info = {
    "token": None,
    "exp": 0,
}

# websocket reference
ws_app = None


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def decode_jwt_exp(token: str) -> int:
    # decode exp จาก JWT โดยไม่ verify signature
    parts = token.split(".")
    if len(parts) != 3:
        return 0

    payload = parts[1]
    # เติม padding
    padding = "=" * (-len(payload) % 4)

    import base64
    decoded = base64.urlsafe_b64decode(payload + padding)
    obj = json.loads(decoded.decode("utf-8"))
    return int(obj.get("exp", 0))


def fetch_new_token():
    url = f"{BASE_URL}/api/auth/login/public"
    r = requests.post(url, json={"publicId": PUBLIC_ID}, timeout=15)
    r.raise_for_status()

    data = r.json()
    token = data["token"]
    exp = decode_jwt_exp(token)

    token_info["token"] = token
    token_info["exp"] = exp

    exp_text = datetime.fromtimestamp(exp).strftime("%Y-%m-%d %H:%M:%S") if exp else "unknown"
    print(f"[{now_str()}] token refreshed, exp={exp_text}")


def token_needs_refresh() -> bool:
    token = token_info.get("token")
    exp = token_info.get("exp", 0)

    if not token or not exp:
        return True

    return time.time() >= (exp - TOKEN_REFRESH_MARGIN)


def ensure_token():
    if token_needs_refresh():
        fetch_new_token()


def build_subscribe_payload():
    keys = [
        {"type": "ATTRIBUTE", "key": "perimeter"},
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

    return {
        "cmds": [
            {
                "type": "ENTITY_DATA",
                "query": {
                    "entityFilter": {
                        "type": "deviceType",
                        "resolveMultiple": True,
                        # "deviceTypes": ["bus", "busstop"],
                        "deviceTypes": ["bus"],
                        "deviceNameFilter": ""
                    },
                    "pageLink": {
                        "page": 0,
                        "pageSize": 16384,
                        "textSearch": None,
                        "dynamic": True
                    },
                    "entityFields": [
                        {"type": "ENTITY_FIELD", "key": "name"},
                        {"type": "ENTITY_FIELD", "key": "label"},
                        {"type": "ENTITY_FIELD", "key": "additionalInfo"}
                    ],
                    "latestValues": keys
                },
                "latestCmd": {
                    "keys": keys
                },
                "cmdId": 1
            }
        ]
    }


def merge_latest_section(target: dict, source: dict, section: str):
    if section not in source:
        return
    if section not in target:
        target[section] = {}
    target[section].update(source[section])


def merge_entity(item: dict):
    entity_id = item["entityId"]["id"]

    with state_lock:
        if entity_id not in bus_state:
            bus_state[entity_id] = {
                "entityId": item["entityId"],
                "ENTITY_FIELD": {},
                "ATTRIBUTE": {},
                "TIME_SERIES": {},
                "updated_at": None,
            }

        latest = item.get("latest", {})

        merge_latest_section(bus_state[entity_id], latest, "ENTITY_FIELD")
        merge_latest_section(bus_state[entity_id], latest, "ATTRIBUTE")
        merge_latest_section(bus_state[entity_id], latest, "TIME_SERIES")
        bus_state[entity_id]["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_value(entity: dict, section: str, key: str):
    return entity.get(section, {}).get(key, {}).get("value")


def get_ts(entity: dict, section: str, key: str):
    return entity.get(section, {}).get(key, {}).get("ts")


def print_bus_table():
    with state_lock:
        rows = []
        for entity_id, entity in bus_state.items():
            name = get_value(entity, "ENTITY_FIELD", "name") or "-"
            label = get_value(entity, "ENTITY_FIELD", "label") or "-"
            lat = get_value(entity, "TIME_SERIES", "latitude") or "-"
            lon = get_value(entity, "TIME_SERIES", "longitude") or "-"
            speed = get_value(entity, "TIME_SERIES", "speed") or "-"
            status = get_value(entity, "TIME_SERIES", "status") or "-"
            seats = get_value(entity, "TIME_SERIES", "availableSeats") or "-"
            people_in = get_value(entity, "TIME_SERIES", "peopleIn") or "-"
            people_out = get_value(entity, "TIME_SERIES", "peopleOut") or "-"
            ts = get_ts(entity, "TIME_SERIES", "latitude") or get_ts(entity, "TIME_SERIES", "speed") or 0

            rows.append({
                "entity_id": entity_id,
                "name": name,
                "label": label,
                "lat": lat,
                "lon": lon,
                "speed": speed,
                "status": status,
                "seats": seats,
                "people_in": people_in,
                "people_out": people_out,
                "ts": ts,
            })

        rows.sort(key=lambda x: (x["name"] != "-", x["name"]), reverse=False)

    os.system("cls" if os.name == "nt" else "clear")
    print(f"[{now_str()}] tracked entities: {len(rows)}")
    print("-" * 140)
    print(f"{'NAME':25} {'LABEL':8} {'LAT':12} {'LON':12} {'SPEED':8} {'STATUS':18} {'SEATS':6} {'IN':4} {'OUT':4} {'TS':13}")
    print("-" * 140)

    for r in rows:
        print(
            f"{str(r['name'])[:25]:25} "
            f"{str(r['label'])[:8]:8} "
            f"{str(r['lat'])[:12]:12} "
            f"{str(r['lon'])[:12]:12} "
            f"{str(r['speed'])[:8]:8} "
            f"{str(r['status'])[:18]:18} "
            f"{str(r['seats'])[:6]:6} "
            f"{str(r['people_in'])[:4]:4} "
            f"{str(r['people_out'])[:4]:4} "
            f"{str(r['ts'])[:13]:13}"
        )

    print("-" * 140)


def print_single_update(item: dict):
    entity_id = item["entityId"]["id"]

    with state_lock:
        entity = bus_state.get(entity_id, {})

    name = get_value(entity, "ENTITY_FIELD", "name") or entity_id
    lat = get_value(entity, "TIME_SERIES", "latitude") or "-"
    lon = get_value(entity, "TIME_SERIES", "longitude") or "-"
    speed = get_value(entity, "TIME_SERIES", "speed") or "-"
    status = get_value(entity, "TIME_SERIES", "status") or "-"
    seats = get_value(entity, "TIME_SERIES", "availableSeats") or "-"

    print(f"[{now_str()}] update: {name} | lat={lat} lon={lon} speed={speed} status={status} seats={seats}")


def send_auth_and_subscribe(ws):
    ensure_token()

    auth_payload = {
        "authCmd": {
            "cmdId": 0,
            "token": token_info["token"]
        }
    }
    ws.send(json.dumps(auth_payload))
    print(f"[{now_str()}] sent auth")

    subscribe_payload = build_subscribe_payload()
    ws.send(json.dumps(subscribe_payload))
    print(f"[{now_str()}] sent subscribe")


def on_open(ws):
    print(f"[{now_str()}] websocket connected")
    send_auth_and_subscribe(ws)


def on_message(ws, message):
    try:
        msg = json.loads(message)
    except Exception as e:
        print(f"[{now_str()}] invalid json: {e}")
        return

    if msg.get("errorCode", 0) != 0:
        print(f"[{now_str()}] server error: {msg.get('errorMsg')}")
        return

    # initial snapshot
    if msg.get("data") and msg["data"].get("data"):
        for item in msg["data"]["data"]:
            merge_entity(item)
        print(f"[{now_str()}] initial snapshot received: {len(msg['data']['data'])} entities")
        print_bus_table()

    # incremental updates
    if msg.get("update"):
        for item in msg["update"]:
            merge_entity(item)
            print_single_update(item)
        print_bus_table()


def on_error(ws, error):
    print(f"[{now_str()}] websocket error: {error}")


def on_close(ws, code, msg):
    print(f"[{now_str()}] websocket closed: code={code}, msg={msg}")


def token_refresh_watcher():
    global ws_app

    while True:
        try:
            time.sleep(5)

            if token_needs_refresh():
                print(f"[{now_str()}] token nearing expiry, refreshing and reconnecting...")
                fetch_new_token()

                # บังคับ reconnect เพื่อใช้ token ใหม่
                if ws_app is not None:
                    try:
                        ws_app.close()
                    except Exception as e:
                        print(f"[{now_str()}] close ws failed: {e}")

        except Exception as e:
            print(f"[{now_str()}] token watcher error: {e}")


def run_forever():
    global ws_app

    while True:
        try:
            ensure_token()

            ws_app = websocket.WebSocketApp(
                WS_URL,
                header={"Origin": BASE_URL},
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )

            ws_app.run_forever(
                ping_interval=PING_INTERVAL,
                ping_timeout=PING_TIMEOUT
            )

        except KeyboardInterrupt:
            print(f"\n[{now_str()}] stopped by user")
            break
        except Exception as e:
            print(f"[{now_str()}] main loop error: {e}")

        print(f"[{now_str()}] reconnecting in 3 seconds...")
        time.sleep(3)


if __name__ == "__main__":
    watcher = threading.Thread(target=token_refresh_watcher, daemon=True)
    watcher.start()
    run_forever()