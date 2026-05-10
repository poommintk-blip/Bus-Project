import requests
import websocket
import json
import time
import threading
import os
import googlemaps
import base64
from datetime import datetime
from geopy.geocoders import Nominatim
from geopy.exc import GeopyError

# --- 2. สร้างตัวแปลงพิกัด (วางไว้แถวๆ ตัวแปร gmaps เดิม) ---
# user_agent ตั้งเป็นชื่ออะไรก็ได้ครับ
geolocator = Nominatim(user_agent="sut_bus_tracker_v1")

# --- 3. แก้ไขฟังก์ชัน get_place_name เป็นแบบนี้ ---
def get_place_name(lat, lon):
    if lat == "-" or lon == "-" or lat is None:
        return "-"
    
    try:
        # Cache key: ปัดทศนิยมเพื่อให้ประหยัดการดึงข้อมูล
        cache_key = (round(float(lat), 4), round(float(lon), 4))
    except:
        return "-"

    with location_lock:
        if cache_key in location_cache:
            return location_cache[cache_key]

    try:
        # ดึงข้อมูลจาก OpenStreetMap แทน Google
        location = geolocator.reverse(f"{lat}, {lon}", language='th', timeout=10)
        if location:
            # ดึงชื่อสถานที่ส่วนแรก (เช่น ชื่อตึก หรือชื่อถนน)
            name = location.address.split(',')[0]
            with location_lock:
                location_cache[cache_key] = name
            return name
    except Exception as e:
        # หากดึงไม่ได้ (เช่น Internet ช้า) ให้ส่งข้อความบอก
        return "กำลังค้นหา..."
    
    return "ไม่พบชื่อสถานที่"

# --- CONFIGURATION ---
BASE_URL = "http://203.158.3.33:8080"
WS_URL = "ws://203.158.3.33:8080/api/ws"
PUBLIC_ID = "44a00910-fa93-11ef-94ed-973314b03447"
# ใส่ API Key ของคุณที่นี่
GOOGLE_MAPS_API_KEY = "AIzaSyCdtTOIpwUcxwG_6l6tkU-Isff8gK4NtUM" 

# --- INITIALIZE CLIENTS ---
try:
    gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)
except Exception as e:
    print(f"Google Maps Config Error: {e}")

# --- STATE MANAGEMENT ---
bus_state = {}
state_lock = threading.Lock()
location_cache = {}
location_lock = threading.Lock()
token_info = {"token": None, "exp": 0}
ws_app = None

# --- UTILS ---
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def decode_jwt_exp(token: str) -> int:
    try:
        parts = token.split(".")
        if len(parts) != 3: return 0
        payload = parts[1]
        padding = "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload + padding)
        obj = json.loads(decoded.decode("utf-8"))
        return int(obj.get("exp", 0))
    except: return 0

def fetch_new_token():
    try:
        url = f"{BASE_URL}/api/auth/login/public"
        r = requests.post(url, json={"publicId": PUBLIC_ID}, timeout=15)
        r.raise_for_status()
        data = r.json()
        token = data["token"]
        token_info["token"] = token
        token_info["exp"] = decode_jwt_exp(token)
        print(f"[{now_str()}] Token refreshed.")
    except Exception as e:
        print(f"[{now_str()}] Fetch token error: {e}")

def ensure_token():
    if not token_info["token"] or time.time() >= (token_info["exp"] - 60):
        fetch_new_token()

# --- GEOCODING LOGIC ---
def get_place_name(lat, lon):
    if lat == "-" or lon == "-" or lat is None:
        return "-"
    try:
        cache_key = (round(float(lat), 4), round(float(lon), 4))
    except:
        return "-"

    with location_lock:
        if cache_key in location_cache:
            return location_cache[cache_key]

    try:
        results = gmaps.reverse_geocode((lat, lon), language='th')
        if results:
            name = results[0]['formatted_address'].split(',')[0]
            with location_lock:
                location_cache[cache_key] = name
            return name
    except Exception as e:
        return f"Err: {str(e)[:10]}"
    return "Unknown"

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
                "place": get_place_name(lat, lon),
                "speed": get_value(entity, "TIME_SERIES", "speed") or 0,
                "status": get_value(entity, "TIME_SERIES", "status") or "-",
                "seats": get_value(entity, "TIME_SERIES", "availableSeats") or "-",
            })
    rows.sort(key=lambda x: str(x["name"]))
    os.system("cls" if os.name == "nt" else "clear")
    print(f"[{now_str()}] SUT BUS TRACKER (Reverse Geocoding Active)")
    print("-" * 165)
    print(f"{'NAME':20} {'LABEL':8} {'LAT':12} {'LON':12} {'LOCATION (GOOGLE)':35} {'SPEED':8} {'STATUS':15} {'SEATS':5}")
    print("-" * 165)
    for r in rows:
        print(f"{str(r['name'])[:20]:20} {str(r['label'])[:8]:8} {str(r['lat'])[:12]:12} "
              f"{str(r['lon'])[:12]:12} {str(r['place'])[:35]:35} {str(r['speed'])[:8]:8} "
              f"{str(r['status'])[:15]:15} {str(r['seats'])[:5]:5}")
    print("-" * 165)

# --- WEBSOCKET HANDLERS ---
def on_message(ws, message):
    try:
        msg = json.loads(message)
        
        # 1. ตรวจสอบข้อมูลตั้งต้น (Initial Snapshot)
        # เพิ่มการเช็ค msg.get("data") และ msg["data"].get("data") ว่าไม่เป็น None
        data_section = msg.get("data")
        if data_section and data_section.get("data"):
            for item in data_section["data"]: 
                merge_entity(item)
        
        # 2. ตรวจสอบข้อมูลที่อัปเดต (Incremental Updates)
        # เพิ่มการเช็ค msg.get("update") ว่าไม่เป็น None
        update_section = msg.get("update")
        if update_section: # ถ้า update_section เป็น None เงื่อนไขนี้จะไม่ทำงาน
            for item in update_section: 
                merge_entity(item)
        
        # แสดงผลตาราง
        print_bus_table() 
        
    except Exception as e:
        # พิมพ์ Error ออกมาดูเพื่อ debug แต่ไม่ให้โปรแกรมหยุดทำงาน
        print(f"[{now_str()}] Skip message due to format: {e}")

def on_open(ws):
    ensure_token()
    ws.send(json.dumps({"authCmd": {"cmdId": 0, "token": token_info["token"]}}))
    keys = [{"type": "TIME_SERIES", "key": k} for k in ["latitude", "longitude", "speed", "status", "availableSeats"]]
    sub_payload = {
        "cmds": [{"type": "ENTITY_DATA", "query": {"entityFilter": {"type": "deviceType", "resolveMultiple": True, "deviceTypes": ["bus"], "deviceNameFilter": ""},
                  "pageLink": {"page": 0, "pageSize": 100, "dynamic": True},
                  "entityFields": [{"type": "ENTITY_FIELD", "key": "name"}, {"type": "ENTITY_FIELD", "key": "label"}],
                  "latestValues": keys}, "latestCmd": {"keys": keys}, "cmdId": 1}]
    }
    ws.send(json.dumps(sub_payload))

def token_refresh_watcher():
    global ws_app
    while True:
        try:
            time.sleep(10)
            if token_info["token"] and time.time() >= (token_info["exp"] - 60):
                print(f"[{now_str()}] Token nearing expiry, refreshing...")
                fetch_new_token()
                if ws_app:
                    ws_app.close()
        except Exception as e:
            print(f"Watcher error: {e}")

def run_forever():
    global ws_app
    while True:
        try:
            ensure_token()
            ws_app = websocket.WebSocketApp(WS_URL, header={"Origin": BASE_URL}, 
                                           on_open=on_open, on_message=on_message)
            ws_app.run_forever(ping_interval=20, ping_timeout=10)
        except Exception as e:
            print(f"Connection Error: {e}")
        time.sleep(5)
        
# --- แก้ไขส่วน GEOCODING LOGIC ให้เหลือแค่นี้พอครับ ---

def get_place_name(lat, lon):
    if lat == "-" or lon == "-" or lat is None:
        return "-"
    
    try:
        cache_key = (round(float(lat), 4), round(float(lon), 4))
    except:
        return "-"

    with location_lock:
        if cache_key in location_cache:
            return location_cache[cache_key]

    try:
        # ดึงข้อมูลแบบละเอียด (address-level)
        location = geolocator.reverse(f"{lat}, {lon}", language='th', timeout=10)
        if location:
            # ดึงข้อมูลดิบแบบ Dictionary เพื่อเลือกส่วนที่ต้องการ
            raw = location.raw.get('address', {})
            
            # ลำดับความสำคัญ: ชื่อตึก/สถานที่ > ถนน > ย่าน
            # เราจะดึงข้อมูลที่ "เฉพาะเจาะจง" ที่สุดมาแสดง
            place = (
                raw.get('amenity') or      # ชื่อสถานที่สำคัญ
                raw.get('building') or     # ชื่อตึก
                raw.get('tourism') or      # จุดท่องเที่ยว
                raw.get('highway') or      # ชื่อถนน
                raw.get('suburb') or       # ย่าน/หมู่บ้าน
                raw.get('village') or      # หมู่บ้าน
                "มทส."                     # ค่าเริ่มต้นถ้าอยู่ในเขต มทส.
            )
            
            with location_lock:
                location_cache[cache_key] = place
            return place
    except Exception:
        return "กำลังค้นหา..."
    
    return "ไม่พบข้อมูล"

if __name__ == "__main__":
    watcher = threading.Thread(target=token_refresh_watcher, daemon=True)
    watcher.start()
    print(f"[{now_str()}] Starting Bus Tracking System...")
    run_forever()