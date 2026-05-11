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

# อัปเดตพิกัดให้ตรงกับไฟล์หลักเพื่อให้แสดงชื่อสถานที่ตรงกัน
SUT_LOCATIONS = [
    {"name": "หอพักหญิง S1-S6", "lat": 14.8765, "lon": 102.0165},
    {"name": "หอพักชาย S7-S12", "lat": 14.8752, "lon": 102.0188},
    {"name": "หอพักชาย S13-S14", "lat": 14.8735, "lon": 102.0195},
    {"name": "หอพักหญิง S15", "lat": 14.8768, "lon": 102.0215},
    {"name": "หอพักหญิง S16, S18", "lat": 14.8760, "lon": 102.0225},
    {"name": "อาคารเรียนรวม 1 (B1)", "lat": 14.8824, "lon": 102.0205},
    {"name": "อาคารเรียนรวม 2 (B2)", "lat": 14.8812, "lon": 102.0209},
    {"name": "ศูนย์บรรณสาร (ห้องสมุด)", "lat": 14.8795, "lon": 102.0198},
    {"name": "อาคารส่วนกิจการนักศึกษา", "lat": 14.8815, "lon": 102.0182},
    {"name": "อาคารสุรเริงไชย", "lat": 14.8810, "lon": 102.0175},
    {"name": "โรงอาหารกาสะลองคำ", "lat": 14.8775, "lon": 102.0228},
    {"name": "อาคารบริหาร (AD)", "lat": 14.8818, "lon": 102.0175},
    {"name": "เทคโนธานี", "lat": 14.8963, "lon": 102.0124},
]

# --- INITIALIZE ---
geolocator = Nominatim(user_agent="sut_bus_client_final")
bus_state = {}
state_lock = threading.Lock()
token_info = {"token": None, "exp": 0}

# --- FUNCTIONS ---
def calculate_distance(lat1, lon1, lat2, lon2):
    try: return math.sqrt((float(lat1) - lat2)**2 + (float(lon1) - lon2)**2) * 111319
    except: return 999

def get_place_name(lat, lon):
    if lat == "-" or lon == "-" or lat is None: return "-"
    try:
        curr_lat, curr_lon = float(lat), float(lon)
        # ใช้รัศมี 200 เมตรตามที่ตกลงกันไว้
        for loc in SUT_LOCATIONS:
            if calculate_distance(curr_lat, curr_lon, loc["lat"], loc["lon"]) < 200:
                return f"{loc['name']}"
        return "พื้นที่ภายใน มทส."
    except: return "มทส."

def fetch_new_token():
    try:
        r = requests.post(f"{BASE_URL}/api/auth/login/public", json={"publicId": PUBLIC_ID}, timeout=10)
        token = r.json()["token"]
        token_info["token"] = token
        payload = token.split(".")[1]
        token_info["exp"] = json.loads(base64.urlsafe_b64decode(payload + "==")).get("exp", 0)
    except: pass

def get_value(entity, section, key):
    return entity.get(section, {}).get(key, {}).get("value")

def on_message(ws, message):
    try:
        msg = json.loads(message)
        data = msg.get("data", {}).get("data") or msg.get("update")
        if data:
            with state_lock:
                for item in data:
                    eid = item["entityId"]["id"]
                    if eid not in bus_state: bus_state[eid] = {"ENTITY_FIELD": {}, "TIME_SERIES": {}}
                    latest = item.get("latest", {})
                    for sec in ["ENTITY_FIELD", "TIME_SERIES"]:
                        if sec in latest: bus_state[eid][sec].update(latest[sec])
    except: pass

def run_ws():
    while True:
        try:
            if not token_info["token"] or time.time() >= (token_info["exp"] - 60): fetch_new_token()
            ws = websocket.WebSocketApp(WS_URL, header={"Origin": BASE_URL}, on_message=on_message)
            ws.on_open = lambda ws: ws.send(json.dumps({
                "authCmd": {"cmdId": 0, "token": token_info["token"]},
                "cmds": [{
                    "type": "ENTITY_DATA", 
                    "query": {
                        "entityFilter": {"type": "deviceType", "resolveMultiple": True, "deviceTypes": ["bus"]},
                        "pageLink": {"page": 0, "pageSize": 100}, 
                        "entityFields": [{"type": "ENTITY_FIELD", "key": "name"}], 
                        "latestValues": [{"type": "TIME_SERIES", "key": k} for k in ["latitude", "longitude", "availableSeats", "name"]]
                    }, 
                    "cmdId": 1
                }]
            }))
            ws.run_forever(ping_interval=15)
        except: time.sleep(5)

def run_client_ui():
    time.sleep(3)
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        print("\n=== SUT BUS TRACKING MENU ===")
        print("0: ดูรถทั้งหมด (Track All)")
        
        current_buses = []
        with state_lock:
            for eid, values in bus_state.items():
                name = get_value(values, "ENTITY_FIELD", "name")
                if name and name != "-": current_buses.append(name)
        
        current_buses.sort()
        for i, name in enumerate(current_buses, 1): print(f"{i}: {name}")
        
        choice = input("\nChoice (หรือ 0): ")
        target = current_buses[int(choice)-1] if choice.isdigit() and 0 < int(choice) <= len(current_buses) else "ALL"

        while True:
            try:
                os.system("cls" if os.name == "nt" else "clear")
                print(f"--- Tracking: {target} | {time.strftime('%H:%M:%S')} ---")
                # ปรับช่องว่างให้กระชับ: NAME(18), LOCATION(30), SEATS(10)
                print(f"{'NAME':18} {'LOCATION (SUT)':30} {'SEATS LEFT':10}")
                print("-" * 65)

                with state_lock:
                    for eid, values in bus_state.items():
                        name = get_value(values, "ENTITY_FIELD", "name")
                        if target == "ALL" or target == name:
                            lat = get_value(values, "TIME_SERIES", "latitude")
                            lon = get_value(values, "TIME_SERIES", "longitude")
                            seats = get_value(values, "TIME_SERIES", "availableSeats")
                            
                            d_name = str(name or "Unknown")[:18]
                            d_place = str(get_place_name(lat, lon))[:30]
                            d_seats = str(seats if seats is not None else "0")
                            
                            print(f"{d_name:18} {d_place:30} {d_seats:10}")
                
                print("-" * 65)
                print("(Press Ctrl+C to back to menu)")
                time.sleep(1.5)
            except KeyboardInterrupt: break
            except Exception as e:
                time.sleep(2)
                break

if __name__ == "__main__":
    threading.Thread(target=run_ws, daemon=True).start()
    run_client_ui()