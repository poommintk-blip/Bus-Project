import requests
import websocket
import json
import time
import threading
import os
import base64
import math
from datetime import datetime
from geopy.geocoders import Nominatim

# --- CONFIGURATION ---
BASE_URL = "http://203.158.3.33:8080"
WS_URL = "ws://203.158.3.33:8080/api/ws"
PUBLIC_ID = "44a00910-fa93-11ef-94ed-973314b03447"

SUT_LOCATIONS = [
    # --- กลุ่มหอพัก (S) ---
    {"name": "หอพักหญิง S1-S6", "lat": 14.8765, "lon": 102.0165},
    {"name": "หอพักชาย S7-S12", "lat": 14.8752, "lon": 102.0188},
    {"name": "หอพักชาย S13-S14", "lat": 14.8735, "lon": 102.0195},
    {"name": "หอพักหญิง S15", "lat": 14.8768, "lon": 102.0215},
    {"name": "หอพักหญิง S16, S18", "lat": 14.8760, "lon": 102.0225},
    
    # --- กลุ่มอาคารเรียนและสำนักงาน ---
    {"name": "อาคารเรียนรวม 1 (B1)", "lat": 14.8824, "lon": 102.0205},
    {"name": "อาคารเรียนรวม 2 (B2)", "lat": 14.8812, "lon": 102.0209},
    {"name": "ศูนย์บรรณสาร (ห้องสมุด)", "lat": 14.8795, "lon": 102.0198},
    {"name": "อาคารส่วนกิจการนักศึกษา", "lat": 14.8815, "lon": 102.0182},
    {"name": "อาคารสุรเริงไชย", "lat": 14.8810, "lon": 102.0178},
    {"name": "อาคารขนส่ง (จุดเริ่มต้นสายสีส้ม/แดง)", "lat": 14.8725, "lon": 102.0235},
    
    # --- กลุ่มศูนย์เครื่องมือและโรงอาหาร ---
    {"name": "โรงอาหารกาสะลองคำ", "lat": 14.8775, "lon": 102.0228},
    {"name": "ศูนย์เครื่องมือ F1, F2, F4", "lat": 14.8805, "lon": 102.0155},
    {"name": "ศูนย์เครื่องมือ F3, F5, F6", "lat": 14.8798, "lon": 102.0145},
    {"name": "ศูนย์เครื่องมือ F9", "lat": 14.8802, "lon": 102.0132},
    {"name": "ครัวท่านท้าว", "lat": 14.8792, "lon": 102.0140},
    
    # --- จุดภายนอกและโรงพยาบาล ---
    {"name": "รพ. มทส. / ศูนย์ความพึงพอใจ", "lat": 14.8745, "lon": 102.0035},
    {"name": "เทคโนธานี", "lat": 14.8963, "lon": 102.0124},
    {"name": "สุรสัมมนาคาร / รร.สุรวิวัฒน์", "lat": 14.8855, "lon": 102.0065},
    {"name": "ตลาดหน้า มทส. (จุดเริ่มต้นสายสีเหลือง)", "lat": 14.9015, "lon": 102.0275},
]

# --- INITIALIZE ---
geolocator = Nominatim(user_agent="sut_bus_tracker_v2")
bus_state = {}
state_lock = threading.Lock()
location_cache = {}
last_bus_positions = {}
token_info = {"token": None, "exp": 0}
ws_app = None

# --- FUNCTIONS ---
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def calculate_distance(lat1, lon1, lat2, lon2):
    try:
        return math.sqrt((float(lat1) - lat2)**2 + (float(lon1) - lon2)**2) * 111319
    except:
        return 9999

def get_place_name(entity_id, lat, lon):
    if lat == "-" or lon == "-" or lat is None: return "-"
    try:
        curr_lat, curr_lon = float(lat), float(lon)
        
        # 1. เช็คพิกัดตึกในลิสต์ (ขยายรัศมีเป็น 250 เมตรเพื่อให้ครอบคลุมอาคารใหญ่)
        for loc in SUT_LOCATIONS:
            if calculate_distance(curr_lat, curr_lon, loc["lat"], loc["lon"]) < 250:
                return f"{loc['name']}"

        # 2. หากไม่อยู่ใกล้ตึกในลิสต์ ให้พยายามดึงชื่อจริงจาก Geopy มาแสดง (แทนการใช้ "มทส.")
        cache_key = (round(curr_lat, 4), round(curr_lon, 4))
        with location_lock:
            if cache_key in location_cache: 
                return location_cache[cache_key]

        # ดึงข้อมูลจากระบบแผนที่ฟรี
        location = geolocator.reverse(f"{lat}, {lon}", language='th', timeout=3)
        if location:
            raw = location.raw.get('address', {})
            # ดึงชื่อที่เจาะจงที่สุดเท่าที่หาได้
            res = raw.get('amenity') or raw.get('building') or raw.get('road') or raw.get('suburb') or "ภายใน มทส."
            
            with location_lock:
                location_cache[cache_key] = res
            return res
            
    except:
        return "ค้นหาตำแหน่ง..."
    
    return "ภายใน มทส."

def fetch_new_token():
    try:
        r = requests.post(f"{BASE_URL}/api/auth/login/public", json={"publicId": PUBLIC_ID}, timeout=10)
        r.raise_for_status()
        token = r.json()["token"]
        token_info["token"] = token
        payload = token.split(".")[1]
        token_info["exp"] = json.loads(base64.urlsafe_b64decode(payload + "==")).get("exp", 0)
        print(f"[{now_str()}] Token refreshed.")
    except Exception as e:
        print(f"Token Error: {e}")

def get_value(entity, section, key):
    return entity.get(section, {}).get(key, {}).get("value")

def merge_entity(item):
    entity_id = item["entityId"]["id"]
    with state_lock:
        if entity_id not in bus_state:
            bus_state[entity_id] = {"ENTITY_FIELD": {}, "TIME_SERIES": {}}
        latest = item.get("latest", {})
        for sec in ["ENTITY_FIELD", "TIME_SERIES"]:
            if sec in latest: bus_state[entity_id][sec].update(latest[sec])

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
                "place": get_place_name(eid, lat, lon),
                "speed": get_value(entity, "TIME_SERIES", "speed") or 0,
                "status": get_value(entity, "TIME_SERIES", "status") or "-",
            })
    
    rows.sort(key=lambda x: str(x["name"]))
    
    os.system("cls" if os.name == "nt" else "clear")
    print(f"[{now_str()}] SUT BUS REAL-TIME TRACKER (Optimized View)")
    # ปรับความยาวเส้นคั่นให้พอดีกับคอลัมน์ใหม่
    print("-" * 135)
    # ปรับความกว้างคอลัมน์: NAME(18), LAT(12), LON(12), LOCATION(30), SPEED(10), STATUS(15)
    print(f"{'NAME':18} {'LAT':12} {'LON':12} {'LOCATION (SUT)':30} {'SPEED (km/h)':15} {'STATUS':15}")
    print("-" * 135)
    
    for r in rows:
        # ใช้การจัดรูปแบบที่กระชับขึ้นเพื่อลดช่องว่าง
        name = str(r['name'])[:18]
        lat = str(r['lat'])[:10]
        lon = str(r['lon'])[:10]
        place = str(r['place'])[:30]
        speed = f"{float(r['speed']):>6.2f}" # จัดชิดขวาและแสดงทศนิยม 2 ตำแหน่ง
        status = str(r['status'])[:15]
        
        print(f"{name:18} {lat:12} {lon:12} {place:30} {speed:15} {status:15}")
    print("-" * 135)
def on_message(ws, message):
    try:
        msg = json.loads(message)
        # ตรวจสอบโครงสร้างข้อมูลที่ส่งมาและ merge เข้า state
        data_block = msg.get("data", {}).get("data") or msg.get("update")
        if data_block:
            for item in data_block: merge_entity(item)
    except: pass

def on_open(ws):
    ensure_token()
    # ส่งคำสั่งยืนยันตัวตน
    ws.send(json.dumps({"authCmd": {"cmdId": 0, "token": token_info["token"]}}))
    # ส่งคำสั่งดึงข้อมูลรถทั้งหมด (Query)
    keys = [{"type": "TIME_SERIES", "key": k} for k in ["latitude", "longitude", "speed", "status"]]
    sub = {"cmds": [{"type": "ENTITY_DATA", "query": {"entityFilter": {"type": "deviceType", "resolveMultiple": True, "deviceTypes": ["bus"]},
           "pageLink": {"page": 0, "pageSize": 100}, "entityFields": [{"type": "ENTITY_FIELD", "key": "name"}], "latestValues": keys}, "cmdId": 1}]}
    ws.send(json.dumps(sub))

def ensure_token():
    if not token_info["token"] or time.time() >= (token_info["exp"] - 60):
        fetch_new_token()

def run_forever():
    global ws_app
    while True:
        try:
            ensure_token()
            ws_app = websocket.WebSocketApp(WS_URL, header={"Origin": BASE_URL}, on_open=on_open, on_message=on_message)
            ws_app.run_forever(ping_interval=15, ping_timeout=10)
        except: time.sleep(5)

def auto_refresh_table():
    while True:
        try: print_bus_table()
        except: pass
        time.sleep(1)

if __name__ == "__main__":
    # เริ่มระบบรีเฟรชตารางใน Background
    threading.Thread(target=auto_refresh_table, daemon=True).start()
    # เริ่ม WebSocket ใน Main Thread
    print(f"[{now_str()}] Starting Real-time Bus Tracker...")
    run_forever()