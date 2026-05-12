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

# --- BUS STOPS IN SUT (6 สถานี) ---
BUS_STOPS = [
    {"name": "สถานีเชียว", "stops": [
        {"name": "อาคารเรียนรวม 1", "lat": 14.8824, "lon": 102.0205},
        {"name": "อาคารสวนศักดิ์", "lat": 14.8815, "lon": 102.0195},
        {"name": "โรงอาหารกลาง 1", "lat": 14.8778, "lon": 102.0163},
    ]},
    {"name": "สถานีสัมมง", "stops": [
        {"name": "อาคารเรียนรวม 1", "lat": 14.8824, "lon": 102.0205},
        {"name": "อาคารสุรพัฒน์", "lat": 14.8845, "lon": 102.0142},
        {"name": "ประตู 1", "lat": 14.8973, "lon": 102.0253},
    ]},
    {"name": "สถานีสัสม", "stops": [
        {"name": "ห้องสมุด", "lat": 14.8795, "lon": 102.0198},
        {"name": "อาคารบริหาร", "lat": 14.8818, "lon": 102.0175},
        {"name": "เทคโนธานี", "lat": 14.8963, "lon": 102.0124},
    ]},
    {"name": "สถานีนำเจิน", "stops": [
        {"name": "อาคารสวนศักดิ์", "lat": 14.8815, "lon": 102.0195},
        {"name": "ศูนย์บรรณสาร", "lat": 14.8795, "lon": 102.0198},
        {"name": "อาคารบริหาร", "lat": 14.8818, "lon": 102.0175},
    ]},
    {"name": "สถานีแสง", "stops": [
        {"name": "ประตู 1", "lat": 14.8973, "lon": 102.0253},
        {"name": "เทคโนธานี", "lat": 14.8963, "lon": 102.0124},
        {"name": "รพ.มทส.", "lat": 14.8745, "lon": 102.0035},
    ]},
    {"name": "สถานีเตือง", "stops": [
        {"name": "ประตูหลัก", "lat": 14.8845, "lon": 102.0142},
        {"name": "ศูนย์บรรณสาร", "lat": 14.8795, "lon": 102.0198},
        {"name": "รพ.มทส.", "lat": 14.8745, "lon": 102.0035},
    ]},
]

# --- SUT LOCATIONS ---
SUT_LOCATIONS = [
    {"name": "อาคารเรียนรวม 1", "lat": 14.8824, "lon": 102.0205},
    {"name": "อาคารเรียนรวม 2", "lat": 14.8812, "lon": 102.0209},
    {"name": "ศูนย์บรรณสาร", "lat": 14.8795, "lon": 102.0198},
    {"name": "ประตู 1 มทส.", "lat": 14.8973, "lon": 102.0253},
    {"name": "โรงอาหารกลาง 1", "lat": 14.8778, "lon": 102.0163},
    {"name": "อาคารสุรพัฒน์ 2", "lat": 14.8845, "lon": 102.0142},
    {"name": "รพ.มทส.", "lat": 14.8745, "lon": 102.0035},
    {"name": "อาคารบริหาร (AD)", "lat": 14.8818, "lon": 102.0175},
]

# --- STATE MANAGEMENT ---
bus_state = {}
state_lock = threading.Lock()
location_cache = {}
location_lock = threading.Lock()
token_info = {"token": None, "exp": 0}
ws_app = None

# --- INITIALIZE GEOLOCATOR ---
geolocator = Nominatim(user_agent="sut_bus_tracker_v3")

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

def get_location_with_bus_stop(lat, lon):
    """ตรวจสอบป้ายเมล์ก่อน ถ้าใกล้จะแสดงชื่อป้ายเมล์ พร้อมชื่อสถานี"""
    if lat == "-" or lon == "-" or lat is None:
        return "-"

    try:
        curr_lat, curr_lon = float(lat), float(lon)
        
        # 1. ตรวจสอบป้ายเมล์ก่อน (100 เมตร)
        for bus_route in BUS_STOPS:
            for stop in bus_route["stops"]:
                dist = calculate_distance(curr_lat, curr_lon, stop["lat"], stop["lon"])
                if dist < 100:  # ใกล้ป้ายเมล์
                    return f"{stop['name']} [{bus_route['name']}]"
        
        # 2. ถ้าไม่ใกล้ป้ายเมล์ ให้ตรวจสอบตึกที่รู้จัก (80 เมตร)
        for loc in SUT_LOCATIONS:
            dist = calculate_distance(curr_lat, curr_lon, loc["lat"], loc["lon"])
            if dist < 80:
                return loc["name"]
        
        # 3. ถ้าไม่ใกล้อะไร ให้ใช้ Geopy
        cache_key = (round(curr_lat, 4), round(curr_lon, 4))
        with location_lock:
            if cache_key in location_cache:
                return location_cache[cache_key]
        
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
            return place
    except Exception:
        return "กำลังค้นหา..."

    return "ไม่พบข้อมูล"

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
                "label": get_value(entity, "ENTITY_FIELD", "label") or "-",
                "lat": lat or "-",
                "lon": lon or "-",
                "location": get_location_with_bus_stop(lat, lon),
                "speed": get_value(entity, "TIME_SERIES", "speed") or 0,
                "status": get_value(entity, "TIME_SERIES", "status") or "-",
                "seats": get_value(entity, "TIME_SERIES", "availableSeats") or "-",
            })
    
    rows.sort(key=lambda x: str(x["name"]))
    os.system("cls" if os.name == "nt" else "clear")
    print(f"[{now_str()}] SUT BUS TRACKER (Bus Stop Detection Active)")
    print("-" * 140)
    print(f"{'NAME':18} {'LAT':12} {'LON':12} {'LOCATION (Bus Stop Priority)':60} {'SPEED':8} {'STATUS':15} {'SEATS':5}")
    print("-" * 140)
    
    for r in rows:
        lat_str = f"{float(r['lat']):.8f}" if r['lat'] != "-" else "-"
        lon_str = f"{float(r['lon']):.8f}" if r['lon'] != "-" else "-"
        print(
            f"{str(r['name'])[:18]:18} "
            f"{lat_str:12} "
            f"{lon_str:12} "
            f"{str(r['location'])[:60]:60} "
            f"{str(r['speed'])[:8]:8} "
            f"{str(r['status'])[:15]:15} "
            f"{str(r['seats'])[:5]:5}"
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
    location = get_location_with_bus_stop(lat, lon)
    
    print(f"[{now_str()}] [UPDATE] {name} | lat={lat} lon={lon} location={location} speed={speed} status={status}")

# --- WEBSOCKET HANDLERS ---
def on_message(ws, message):
    try:
        msg = json.loads(message)
        
        # Check for errors
        if msg.get("errorCode", 0) != 0:
            print(f"[{now_str()}] [ERROR] Server error: {msg.get('errorMsg')}")
            return
        
        # Initial snapshot
        data_section = msg.get("data")
        if data_section and data_section.get("data"):
            for item in data_section["data"]:
                merge_entity(item)
            print(f"[{now_str()}] [SNAPSHOT] Received {len(data_section['data'])} entities")
            print_bus_table()
        
        # Incremental updates
        update_section = msg.get("update")
        if update_section:
            for item in update_section:
                merge_entity(item)
                print_single_update(item)
            print_bus_table()
    
    except Exception as e:
        print(f"[{now_str()}] [ERROR] Message parse error: {e}")

def on_open(ws):
    print(f"[{now_str()}] [CONNECT] WebSocket connected")
    ensure_token()
    
    # Send authentication
    auth_payload = {
        "authCmd": {
            "cmdId": 0,
            "token": token_info["token"]
        }
    }
    ws.send(json.dumps(auth_payload))
    print(f"[{now_str()}] [OK] Sent authentication")
    
    # Send subscription
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
    print(f"[{now_str()}] [OK] Sent subscription with latestCmd")

def on_error(ws, error):
    print(f"[{now_str()}] [ERROR] WebSocket error: {error}")

def on_close(ws, close_status_code, close_msg):
    print(f"[{now_str()}] [CLOSE] WebSocket closed: code={close_status_code}, msg={close_msg}")

def token_refresh_watcher():
    global ws_app
    while True:
        try:
            time.sleep(10)
            if token_info["token"] and time.time() >= (token_info["exp"] - 60):
                print(f"[{now_str()}] [REFRESH] Token nearing expiry, refreshing...")
                fetch_new_token()
                if ws_app:
                    try:
                        ws_app.close()
                    except Exception as e:
                        print(f"[{now_str()}] [ERROR] Close WebSocket failed: {e}")
        except Exception as e:
            print(f"[{now_str()}] [ERROR] Token watcher error: {e}")

def run_forever():
    global ws_app
    while True:
        try:
            ensure_token()
            print(f"[{now_str()}] [INFO] Starting WebSocket connection...")
            
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
        
        print(f"[{now_str()}] [INFO] Reconnecting in 5 seconds...")
        time.sleep(5)

# --- MAIN ---
if __name__ == "__main__":
    watcher = threading.Thread(target=token_refresh_watcher, daemon=True)
    watcher.start()
    print(f"[{now_str()}] [START] Starting SUT Bus Tracking System...")
    run_forever()