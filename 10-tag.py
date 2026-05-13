import requests
import websocket
import json
import time
import threading
import os
import base64
from datetime import datetime
from geopy.geocoders import Nominatim
import math

# --- CONFIGURATION ---
BASE_URL = "http://203.158.3.33:8080"
WS_URL = "ws://203.158.3.33:8080/api/ws"
PUBLIC_ID = "44a00910-fa93-11ef-94ed-973314b03447"

# --- BUS STOPS IN SUT (6 สาย) - พิกัดแก้ไขให้ตรงกับตำแหน่งจริง ---
BUS_STOPS = [
    {"name": "สายสีเขียว", "stops": [
        {"name": "อาคารเรียนรวม 1", "lat": 14.8822, "lon": 102.0217},
        {"name": "อาคารส่วนกิจการนักศึกษา (หลังใหม่)", "lat": 14.8808, "lon": 102.0192},
        {"name": "หอพักสุรนิเวศ 1", "lat": 14.8786, "lon": 102.0174},
        {"name": "หอพักสุรนิเวศ 15", "lat": 14.8768, "lon": 102.0215},
        {"name": "หอพักสุรนิเวศ 16,18", "lat": 14.8755, "lon": 102.0230},
        {"name": "โรงอาหารกาสะลองคำ", "lat": 14.8780, "lon": 102.0208},  # แก้ไข
        {"name": "หอพักสุรนิเวศ 7-8,11-12", "lat": 14.8770, "lon": 102.0195},  # แก้ไข
        {"name": "หอพักสุรนิเวศ 13 B", "lat": 14.8757, "lon": 102.0185},  # แก้ไข
        {"name": "หอพักสุรนิเวศ 13 A", "lat": 14.8752, "lon": 102.0178},  # แก้ไข
    ]},
    {"name": "สายสีม่วง", "stops": [
        {"name": "อาคารเรียนรวม 1", "lat": 14.8822, "lon": 102.0217},
        {"name": "อาคารส่วนกิจการนักศึกษา (หลังใหม่)", "lat": 14.8808, "lon": 102.0192},
        {"name": "หอพักสุรนิเวศ 1", "lat": 14.8786, "lon": 102.0174},
        {"name": "หอพักสุรนิเวศ 2,14", "lat": 14.8778, "lon": 102.0163},
        {"name": "หอพักสุรนิเวศ 4-5-6", "lat": 14.8765, "lon": 102.0148},  # แก้ไข
    ]},
    {"name": "สายสีส้ม", "stops": [
        {"name": "อาคารขนส่ง", "lat": 14.8821, "lon": 102.0249},  # แก้ไข (เดิม 14.8725, 102.0235)
        {"name": "อาคารเรียนรวม 2", "lat": 14.8815, "lon": 102.0228},  # แก้ไข
        {"name": "อาคารบรรณสาร 1", "lat": 14.8803, "lon": 102.0213},  # แก้ไข
        {"name": "อาคารบรรณสาร 2", "lat": 14.8800, "lon": 102.0205},  # แก้ไข
        {"name": "อาคารศูนย์เครื่องมือ 1-2-4", "lat": 14.8835, "lon": 102.0180},
        {"name": "อาคารศูนย์เครื่องมือ 3-5-6", "lat": 14.8840, "lon": 102.0170},
        {"name": "อาคารศูนย์เครื่องมือ 9-10,11-12", "lat": 14.8850, "lon": 102.0160},
        {"name": "ครัวท่านท้าว", "lat": 14.8860, "lon": 102.0150},
        {"name": "อาคารส่วนกิจการนักศึกษา (หลังเก่า)", "lat": 14.8815, "lon": 102.0185},
    ]},
    {"name": "สายสีน้ำเงิน", "stops": [
        {"name": "อาคารขนส่ง", "lat": 14.8821, "lon": 102.0249},  # แก้ไข (เดิม 14.8725, 102.0235)
        {"name": "สุรสัมมนาคาร", "lat": 14.8930, "lon": 102.0155},
        {"name": "รร.สุรวิวัฒน์", "lat": 14.8850, "lon": 102.0130},
        {"name": "อาคารส่งเสริมสุขภาพ", "lat": 14.8860, "lon": 102.0115},
        {"name": "อาคารศูนย์ความเป็นเลิศ", "lat": 14.8870, "lon": 102.0100},
        {"name": "รพ.มทส.", "lat": 14.8745, "lon": 102.0035},
        {"name": "เทคโนธานี", "lat": 14.8950, "lon": 102.0140},  # แก้ไข
    ]},
    {"name": "สายสีแดง", "stops": [
        {"name": "อาคารขนส่ง", "lat": 14.8821, "lon": 102.0249},  # แก้ไข (เดิม 14.8725, 102.0235)
        {"name": "อาคารเรียนรวม 2", "lat": 14.8815, "lon": 102.0228},  # แก้ไข
        {"name": "อาคารบรรณสาร 1", "lat": 14.8803, "lon": 102.0213},  # แก้ไข
        {"name": "อาคารบรรณสาร 2", "lat": 14.8800, "lon": 102.0205},  # แก้ไข
        {"name": "อาคารศูนย์เครื่องมือ 1-2-4", "lat": 14.8835, "lon": 102.0180},
        {"name": "อาคารศูนย์เครื่องมือ 3-5-6", "lat": 14.8840, "lon": 102.0170},
        {"name": "อาคารศูนย์เครื่องมือ 9-10,11-12", "lat": 14.8850, "lon": 102.0160},
        {"name": "ครัวท่านท้าว", "lat": 14.8860, "lon": 102.0150},
        {"name": "อาคารเรียนรวม 1", "lat": 14.8822, "lon": 102.0217},
        {"name": "อาคารส่วนกิจการนักศึกษา (หลังใหม่)", "lat": 14.8808, "lon": 102.0192},
        {"name": "หอพักสุรนิเวศ 15", "lat": 14.8768, "lon": 102.0215},
        {"name": "หอพักสุรนิเวศ 16,18", "lat": 14.8755, "lon": 102.0230},
        {"name": "โรงอาหารกาสะลองคำ", "lat": 14.8780, "lon": 102.0208},  # แก้ไข
        {"name": "หอพักสุรนิเวศ 7-8,11-12", "lat": 14.8770, "lon": 102.0195},  # แก้ไข
        {"name": "หอพักสุรนิเวศ 13 B", "lat": 14.8757, "lon": 102.0185},  # แก้ไข
        {"name": "หอพักสุรนิเวศ 13 A", "lat": 14.8752, "lon": 102.0178},  # แก้ไข
        {"name": "หอพักสุรนิเวศ 1", "lat": 14.8786, "lon": 102.0174},
        {"name": "หอพักสุรนิเวศ 2,14", "lat": 14.8778, "lon": 102.0163},
        {"name": "หอพักสุรนิเวศ 4-5-6", "lat": 14.8765, "lon": 102.0148},  # แก้ไข
    ]},
    {"name": "สายสีเหลือง", "stops": [
        {"name": "ตลาดหน้า มทส.ประตู 1", "lat": 14.8970, "lon": 102.0250},
        {"name": "หอพักสุรนิเวศ 15", "lat": 14.8768, "lon": 102.0215},
        {"name": "หอพักสุรนิเวศ 16,18", "lat": 14.8755, "lon": 102.0230},
        {"name": "โรงอาหารกาสะลองคำ", "lat": 14.8780, "lon": 102.0208},  # แก้ไข
        {"name": "หอพักสุรนิเวศ 7-8,11-12", "lat": 14.8770, "lon": 102.0195},  # แก้ไข
        {"name": "หอพักสุรนิเวศ 13 B", "lat": 14.8757, "lon": 102.0185},  # แก้ไข
        {"name": "หอพักสุรนิเวศ 13 A", "lat": 14.8752, "lon": 102.0178},  # แก้ไข
        {"name": "หอพักสุรนิเวศ 1", "lat": 14.8786, "lon": 102.0174},
        {"name": "หอพักสุรนิเวศ 2,14", "lat": 14.8778, "lon": 102.0163},
        {"name": "หอพักสุรนิเวศ 4-5-6", "lat": 14.8765, "lon": 102.0148},  # แก้ไข
    ]},
]

# --- STATE MANAGEMENT ---
bus_state = {}
state_lock = threading.Lock()
location_cache = {}
location_lock = threading.Lock()
token_info = {"token": None, "exp": 0}
ws_app = None
need_refresh_display = threading.Event()

# --- UTILITY FUNCTIONS ---
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def decode_jwt_exp(token: str) -> int:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return 0
        payload = parts[1]
        padding = "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload + padding)
        obj = json.loads(decoded.decode("utf-8"))
        return int(obj.get("exp", 0))
    except:
        return 0

def fetch_new_token():
    try:
        url = f"{BASE_URL}/api/auth/login/public"
        r = requests.post(url, json={"publicId": PUBLIC_ID}, timeout=15)
        r.raise_for_status()
        data = r.json()
        token = data["token"]
        token_info["token"] = token
        token_info["exp"] = decode_jwt_exp(token)
        exp_text = datetime.fromtimestamp(token_info["exp"]).strftime("%Y-%m-%d %H:%M:%S") if token_info["exp"] else "unknown"
        print(f"[{now_str()}] [OK] Token refreshed, exp={exp_text}")
    except Exception as e:
        print(f"[{now_str()}] [ERROR] Fetch token failed: {e}")

def ensure_token():
    if not token_info["token"] or time.time() >= (token_info["exp"] - 60):
        fetch_new_token()

def calculate_distance(lat1, lon1, lat2, lon2):
    try:
        return math.sqrt((float(lat1) - lat2)**2 + (float(lon1) - lon2)**2) * 111319
    except:
        return 9999

def get_location_fast(lat, lon):
    """ตรวจสอบป้ายรถเมล์เท่านั้น - รัศมี 10 เมตร ให้แสดงชื่อป้าย ไม่เรียก Geopy (ไม่ block)"""
    if lat == "-" or lon == "-" or lat is None:
        return "-"
    try:
        curr_lat, curr_lon = float(lat), float(lon)

        # ตรวจสอบป้ายรถเมล์ (10 เมตร เท่านั้น)
        nearest_stop = None
        min_dist = 10
        for bus_route in BUS_STOPS:
            for stop in bus_route["stops"]:
                dist = calculate_distance(curr_lat, curr_lon, stop["lat"], stop["lon"])
                if dist < min_dist:
                    min_dist = dist
                    nearest_stop = f"{stop['name']} [{bus_route['name']}]"

        if nearest_stop:
            return nearest_stop

        # ดูจาก cache เท่านั้น ไม่เรียก Geopy
        cache_key = (round(curr_lat, 4), round(curr_lon, 4))
        with location_lock:
            if cache_key in location_cache:
                return location_cache[cache_key]

        # ถ้าไม่มี cache ให้ส่งไป resolve ใน background
        threading.Thread(target=resolve_location_background, args=(lat, lon, cache_key), daemon=True).start()
        return "(กำลังค้นหา...)"
    except:
        return "มทส."

def resolve_location_background(lat, lon, cache_key):
    """เรียก Geopy ใน background thread ไม่ block WebSocket"""
    try:
        geolocator = Nominatim(user_agent="sut_bus_tracker_v3")
        location = geolocator.reverse(f"{lat}, {lon}", language='th', timeout=10)
        if location:
            raw = location.raw.get('address', {})
            place = (
                raw.get('amenity') or
                raw.get('building') or
                raw.get('tourism') or
                raw.get('highway') or
                raw.get('suburb') or
                raw.get('village') or
                "มทส."
            )
            with location_lock:
                location_cache[cache_key] = place
            need_refresh_display.set()
    except:
        pass

# --- CORE LOGIC ---
def get_value(entity, section, key):
    return entity.get(section, {}).get(key, {}).get("value")

def merge_entity(item):
    entity_id = item["entityId"]["id"]
    with state_lock:
        if entity_id not in bus_state:
            bus_state[entity_id] = {
                "ENTITY_FIELD": {}, "ATTRIBUTE": {}, "TIME_SERIES": {}, "updated_at": None
            }
        latest = item.get("latest", {})
        for sec in ["ENTITY_FIELD", "ATTRIBUTE", "TIME_SERIES"]:
            if sec in latest:
                bus_state[entity_id][sec].update(latest[sec])
        bus_state[entity_id]["updated_at"] = now_str()

def print_bus_table():
    rows = []
    with state_lock:
        for eid, entity in bus_state.items():
            lat = get_value(entity, "TIME_SERIES", "latitude")
            lon = get_value(entity, "TIME_SERIES", "longitude")
            rows.append({
                "name": get_value(entity, "ENTITY_FIELD", "name") or "-",
                "lat": lat or "-",
                "lon": lon or "-",
                "location": get_location_fast(lat, lon),
                "speed": get_value(entity, "TIME_SERIES", "speed") or 0,
                "status": get_value(entity, "TIME_SERIES", "status") or "-",
                "seats": get_value(entity, "TIME_SERIES", "availableSeats") or "-",
            })

    rows.sort(key=lambda x: str(x["name"]))
    os.system("cls" if os.name == "nt" else "clear")
    print(f"[{now_str()}] ระบบติดตามรถเมล์ มทส. (อัปเดตอัตโนมัติ) - ป้าย 10 เมตร")
    print("-" * 130)
    print(f"{'ชื่อรถ':18} {'ละติจูด':12} {'ลองจิจูด':12} {'ตำแหน่ง':55} {'ความเร็ว':8} {'สถานะ':15} {'ที่นั่ง':5}")
    print("-" * 130)

    for r in rows:
        lat_str = f"{float(r['lat']):.8f}" if r['lat'] != "-" else "-"
        lon_str = f"{float(r['lon']):.8f}" if r['lon'] != "-" else "-"
        print(
            f"{str(r['name'])[:18]:18} "
            f"{lat_str:12} "
            f"{lon_str:12} "
            f"{str(r['location'])[:55]:55} "
            f"{str(r['speed'])[:8]:8} "
            f"{str(r['status'])[:15]:15} "
            f"{str(r['seats'])[:5]:5}"
        )
    print("-" * 130)

# --- WEBSOCKET HANDLERS ---
def on_message(ws, message):
    try:
        msg = json.loads(message)

        if msg.get("errorCode", 0) != 0:
            print(f"[{now_str()}] [ERROR] Server error: {msg.get('errorMsg')}")
            return

        # Initial snapshot
        data_section = msg.get("data")
        if data_section and data_section.get("data"):
            for item in data_section["data"]:
                merge_entity(item)
            need_refresh_display.set()

        # Incremental updates
        update_section = msg.get("update")
        if update_section:
            for item in update_section:
                merge_entity(item)
            need_refresh_display.set()

    except Exception as e:
        print(f"[{now_str()}] [ERROR] Message parse error: {e}")

def on_open(ws):
    print(f"[{now_str()}] [CONNECT] เชื่อมต่อสำเร็จ")
    ensure_token()

    auth_payload = {
        "authCmd": {
            "cmdId": 0,
            "token": token_info["token"]
        }
    }
    ws.send(json.dumps(auth_payload))

    keys = [
        {"type": "TIME_SERIES", "key": "latitude"},
        {"type": "TIME_SERIES", "key": "longitude"},
        {"type": "TIME_SERIES", "key": "speed"},
        {"type": "TIME_SERIES", "key": "status"},
        {"type": "TIME_SERIES", "key": "availableSeats"}
    ]

    sub_payload = {
        "cmds": [
            {
                "type": "ENTITY_DATA",
                "query": {
                    "entityFilter": {
                        "type": "deviceType",
                        "resolveMultiple": True,
                        "deviceTypes": ["bus"],
                        "deviceNameFilter": ""
                    },
                    "pageLink": {
                        "page": 0,
                        "pageSize": 100,
                        "dynamic": True
                    },
                    "entityFields": [
                        {"type": "ENTITY_FIELD", "key": "name"},
                        {"type": "ENTITY_FIELD", "key": "label"}
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
    ws.send(json.dumps(sub_payload))
    print(f"[{now_str()}] [OK] Subscribe สำเร็จ (latestCmd)")

def on_error(ws, error):
    print(f"[{now_str()}] [ERROR] WebSocket error: {error}")

def on_close(ws, close_status_code, close_msg):
    print(f"[{now_str()}] [CLOSE] WebSocket ปิด: code={close_status_code}")

def display_thread():
    """Thread แยกสำหรับแสดงผล ไม่ block WebSocket"""
    while True:
        need_refresh_display.wait(timeout=3)
        need_refresh_display.clear()

        with state_lock:
            has_data = len(bus_state) > 0

        if has_data:
            print_bus_table()

def token_refresh_watcher():
    global ws_app
    while True:
        try:
            time.sleep(10)
            if token_info["token"] and time.time() >= (token_info["exp"] - 60):
                print(f"[{now_str()}] [REFRESH] Token กำลังหมดอายุ กำลังต่ออายุ...")
                fetch_new_token()
                if ws_app:
                    try:
                        ws_app.close()
                    except Exception as e:
                        print(f"[{now_str()}] [ERROR] ปิด WebSocket ล้มเหลว: {e}")
        except Exception as e:
            print(f"[{now_str()}] [ERROR] Token watcher error: {e}")

def run_forever():
    global ws_app
    while True:
        try:
            ensure_token()
            print(f"[{now_str()}] [INFO] กำลังเชื่อมต่อ WebSocket...")

            ws_app = websocket.WebSocketApp(
                WS_URL,
                header={"Origin": BASE_URL},
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )

            ws_app.run_forever(ping_interval=20, ping_timeout=10)

        except Exception as e:
            print(f"[{now_str()}] [ERROR] Connection failed: {e}")

        print(f"[{now_str()}] [INFO] เชื่อมต่อใหม่ใน 5 วินาที...")
        time.sleep(5)

# --- MAIN ---
if __name__ == "__main__":
    # Thread แสดงผลแยกจาก WebSocket
    threading.Thread(target=display_thread, daemon=True).start()
    threading.Thread(target=token_refresh_watcher, daemon=True).start()

    print(f"[{now_str()}] [START] เริ่มระบบติดตามรถเมล์ มทส....")
    run_forever()