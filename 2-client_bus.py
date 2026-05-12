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

# --- BUS STOPS IN SUT (6 สาย) พร้อมพิกัดจริง ---
BUS_STOPS = [
    {"name": "สายสีเขียว", "stops": [
        {"name": "อาคารเรียนรวม 1", "lat": 14.8822, "lon": 102.0217},
        {"name": "อาคารส่วนกิจการนักศึกษา (หลังใหม่)", "lat": 14.8808, "lon": 102.0192},
        {"name": "หอพักสุรนิเวศ 1", "lat": 14.8786, "lon": 102.0174},
        {"name": "หอพักสุรนิเวศ 15", "lat": 14.8768, "lon": 102.0215},
        {"name": "หอพักสุรนิเวศ 16,18", "lat": 14.8755, "lon": 102.0230},
        {"name": "โรงอาหารกาสะลองคำ", "lat": 14.8762, "lon": 102.0195},
        {"name": "หอพักสุรนิเวศ 7-8,11-12", "lat": 14.8752, "lon": 102.0188},
        {"name": "หอพักสุรนิเวศ 13 B", "lat": 14.8740, "lon": 102.0200},
        {"name": "หอพักสุรนิเวศ 13 A", "lat": 14.8735, "lon": 102.0210},
    ]},
    {"name": "สายสีม่วง", "stops": [
        {"name": "อาคารเรียนรวม 1", "lat": 14.8822, "lon": 102.0217},
        {"name": "อาคารส่วนกิจการนักศึกษา (หลังใหม่)", "lat": 14.8808, "lon": 102.0192},
        {"name": "หอพักสุรนิเวศ 1", "lat": 14.8786, "lon": 102.0174},
        {"name": "หอพักสุรนิเวศ 2,14", "lat": 14.8778, "lon": 102.0163},
        {"name": "หอพักสุรนิเวศ 4-5-6", "lat": 14.8765, "lon": 102.0155},
    ]},
    {"name": "สายสีส้ม", "stops": [
        {"name": "อาคารขนส่ง", "lat": 14.8725, "lon": 102.0235},
        {"name": "อาคารเรียนรวม 2", "lat": 14.8812, "lon": 102.0209},
        {"name": "อาคารบรรณสาร 1", "lat": 14.8795, "lon": 102.0198},
        {"name": "อาคารบรรณสาร 2", "lat": 14.8800, "lon": 102.0195},
        {"name": "อาคารศูนย์เครื่องมือ 1-2-4", "lat": 14.8835, "lon": 102.0180},
        {"name": "อาคารศูนย์เครื่องมือ 3-5-6", "lat": 14.8840, "lon": 102.0170},
        {"name": "อาคารศูนย์เครื่องมือ 9-10,11-12", "lat": 14.8850, "lon": 102.0160},
        {"name": "ครัวท่านท้าว", "lat": 14.8860, "lon": 102.0150},
        {"name": "อาคารส่วนกิจการนักศึกษา (หลังเก่า)", "lat": 14.8815, "lon": 102.0185},
    ]},
    {"name": "สายสีน้ำเงิน", "stops": [
        {"name": "อาคารขนส่ง", "lat": 14.8725, "lon": 102.0235},
        {"name": "สุรสัมมนาคาร", "lat": 14.8830, "lon": 102.0140},
        {"name": "รร.สุรวิวัฒน์", "lat": 14.8850, "lon": 102.0130},
        {"name": "อาคารส่งเสริมสุขภาพ", "lat": 14.8860, "lon": 102.0115},
        {"name": "อาคารศูนย์ความเป็นเลิศ", "lat": 14.8870, "lon": 102.0100},
        {"name": "รพ.มทส.", "lat": 14.8745, "lon": 102.0035},
        {"name": "เทคโนธานี", "lat": 14.8963, "lon": 102.0124},
    ]},
    {"name": "สายสีแดง", "stops": [
        {"name": "อาคารขนส่ง", "lat": 14.8725, "lon": 102.0235},
        {"name": "อาคารเรียนรวม 2", "lat": 14.8812, "lon": 102.0209},
        {"name": "อาคารบรรณสาร 1", "lat": 14.8795, "lon": 102.0198},
        {"name": "อาคารบรรณสาร 2", "lat": 14.8800, "lon": 102.0195},
        {"name": "อาคารศูนย์เครื่องมือ 1-2-4", "lat": 14.8835, "lon": 102.0180},
        {"name": "อาคารศูนย์เครื่องมือ 3-5-6", "lat": 14.8840, "lon": 102.0170},
        {"name": "อาคารศูนย์เครื่องมือ 9-10,11-12", "lat": 14.8850, "lon": 102.0160},
        {"name": "ครัวท่านท้าว", "lat": 14.8860, "lon": 102.0150},
        {"name": "อาคารเรียนรวม 1", "lat": 14.8822, "lon": 102.0217},
        {"name": "อาคารส่วนกิจการนักศึกษา (หลังใหม่)", "lat": 14.8808, "lon": 102.0192},
        {"name": "หอพักสุรนิเวศ 15", "lat": 14.8768, "lon": 102.0215},
        {"name": "หอพักสุรนิเวศ 16,18", "lat": 14.8755, "lon": 102.0230},
        {"name": "โรงอาหารกาสะลองคำ", "lat": 14.8762, "lon": 102.0195},
        {"name": "หอพักสุรนิเวศ 7-8,11-12", "lat": 14.8752, "lon": 102.0188},
        {"name": "หอพักสุรนิเวศ 13 B", "lat": 14.8740, "lon": 102.0200},
        {"name": "หอพักสุรนิเวศ 13 A", "lat": 14.8735, "lon": 102.0210},
        {"name": "หอพักสุรนิเวศ 1", "lat": 14.8786, "lon": 102.0174},
        {"name": "หอพักสุรนิเวศ 2,14", "lat": 14.8778, "lon": 102.0163},
        {"name": "หอพักสุรนิเวศ 4-5-6", "lat": 14.8765, "lon": 102.0155},
    ]},
    {"name": "สายสีเหลือง", "stops": [
        {"name": "ตลาดหน้า มทส.ประตู 1", "lat": 14.8970, "lon": 102.0250},
        {"name": "หอพักสุรนิเวศ 15", "lat": 14.8768, "lon": 102.0215},
        {"name": "หอพักสุรนิเวศ 16,18", "lat": 14.8755, "lon": 102.0230},
        {"name": "โรงอาหารกาสะลองคำ", "lat": 14.8762, "lon": 102.0195},
        {"name": "หอพักสุรนิเวศ 7-8,11-12", "lat": 14.8752, "lon": 102.0188},
        {"name": "หอพักสุรนิเวศ 13 B", "lat": 14.8740, "lon": 102.0200},
        {"name": "หอพักสุรนิเวศ 13 A", "lat": 14.8735, "lon": 102.0210},
        {"name": "หอพักสุรนิเวศ 1", "lat": 14.8786, "lon": 102.0174},
        {"name": "หอพักสุรนิเวศ 2,14", "lat": 14.8778, "lon": 102.0163},
        {"name": "หอพักสุรนิเวศ 4-5-6", "lat": 14.8765, "lon": 102.0155},
    ]},
]

# --- STATE MANAGEMENT ---
bus_state = {}
state_lock = threading.Lock()
location_cache = {}
location_lock = threading.Lock()
token_info = {"token": None, "exp": 0}
ws_app = None

# --- INITIALIZE GEOLOCATOR ---
geolocator = Nominatim(user_agent="sut_bus_client_v4")

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
        print(f"[{now_str()}] [OK] Token refreshed")
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
    if lat == "-" or lon == "-" or lat is None:
        return "-"
    try:
        curr_lat, curr_lon = float(lat), float(lon)

        nearest_stop = None
        min_dist = 100
        for bus_route in BUS_STOPS:
            for stop in bus_route["stops"]:
                dist = calculate_distance(curr_lat, curr_lon, stop["lat"], stop["lon"])
                if dist < min_dist:
                    min_dist = dist
                    nearest_stop = f"{stop['name']} [{bus_route['name']}]"

        if nearest_stop:
            return nearest_stop

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
                "ภายในมทส."
            )
            with location_lock:
                location_cache[cache_key] = place
            return place
    except:
        return "กำลังค้นหา..."
    return "ภายใน มทส. (ไม่พบข้อมูล)"

def get_buses_near_stop(stop_name):
    results = []
    target_stops = []

    for route in BUS_STOPS:
        for stop in route["stops"]:
            if stop_name.lower() in stop["name"].lower():
                target_stops.append({"lat": stop["lat"], "lon": stop["lon"],
                                     "name": stop["name"], "route": route["name"]})

    if not target_stops:
        return results

    with state_lock:
        for eid, entity in bus_state.items():
            lat = get_value(entity, "TIME_SERIES", "latitude")
            lon = get_value(entity, "TIME_SERIES", "longitude")
            if lat and lon and lat != "-" and lon != "-":
                for ts in target_stops:
                    dist = calculate_distance(float(lat), float(lon), ts["lat"], ts["lon"])
                    if dist < 500:
                        results.append({
                            "name": get_value(entity, "ENTITY_FIELD", "name") or "-",
                            "distance": round(dist, 1),
                            "stop": ts["name"],
                            "route": ts["route"],
                            "speed": get_value(entity, "TIME_SERIES", "speed") or 0,
                            "status": get_value(entity, "TIME_SERIES", "status") or "-",
                            "seats": get_value(entity, "TIME_SERIES", "availableSeats") or "-",
                        })

    results.sort(key=lambda x: x["distance"])
    return results

def get_buses_on_route(route_name):
    results = []
    target_route = None

    for route in BUS_STOPS:
        if route_name.lower() in route["name"].lower():
            target_route = route
            break

    if not target_route:
        return results

    with state_lock:
        for eid, entity in bus_state.items():
            lat = get_value(entity, "TIME_SERIES", "latitude")
            lon = get_value(entity, "TIME_SERIES", "longitude")
            if lat and lon and lat != "-" and lon != "-":
                nearest_stop = None
                min_dist = 300
                for stop in target_route["stops"]:
                    dist = calculate_distance(float(lat), float(lon), stop["lat"], stop["lon"])
                    if dist < min_dist:
                        min_dist = dist
                        nearest_stop = stop["name"]

                if nearest_stop:
                    results.append({
                        "name": get_value(entity, "ENTITY_FIELD", "name") or "-",
                        "nearest_stop": nearest_stop,
                        "distance": round(min_dist, 1),
                        "speed": get_value(entity, "TIME_SERIES", "speed") or 0,
                        "status": get_value(entity, "TIME_SERIES", "status") or "-",
                        "seats": get_value(entity, "TIME_SERIES", "availableSeats") or "-",
                    })

    results.sort(key=lambda x: x["distance"])
    return results

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

# --- WEBSOCKET HANDLERS ---
def on_message(ws, message):
    try:
        msg = json.loads(message)
        if msg.get("errorCode", 0) != 0:
            print(f"[{now_str()}] [ERROR] Server: {msg.get('errorMsg')}")
            return

        data_section = msg.get("data")
        if data_section and data_section.get("data"):
            for item in data_section["data"]:
                merge_entity(item)

        update_section = msg.get("update")
        if update_section:
            for item in update_section:
                merge_entity(item)
    except Exception as e:
        print(f"[{now_str()}] [ERROR] Parse: {e}")

def on_open(ws):
    ensure_token()
    auth_payload = {"authCmd": {"cmdId": 0, "token": token_info["token"]}}
    ws.send(json.dumps(auth_payload))

    keys = [
        {"type": "TIME_SERIES", "key": "latitude"},
        {"type": "TIME_SERIES", "key": "longitude"},
        {"type": "TIME_SERIES", "key": "speed"},
        {"type": "TIME_SERIES", "key": "status"},
        {"type": "TIME_SERIES", "key": "availableSeats"}
    ]

    sub_payload = {
        "cmds": [{
            "type": "ENTITY_DATA",
            "query": {
                "entityFilter": {
                    "type": "deviceType",
                    "resolveMultiple": True,
                    "deviceTypes": ["bus"],
                    "deviceNameFilter": ""
                },
                "pageLink": {"page": 0, "pageSize": 100, "dynamic": True},
                "entityFields": [
                    {"type": "ENTITY_FIELD", "key": "name"},
                    {"type": "ENTITY_FIELD", "key": "label"}
                ],
                "latestValues": keys
            },
            "latestCmd": {"keys": keys},
            "cmdId": 1
        }]
    }
    ws.send(json.dumps(sub_payload))
    print(f"[{now_str()}] [OK] เชื่อมต่อสำเร็จ")

def on_error(ws, error):
    print(f"[{now_str()}] [ERROR] WebSocket: {error}")

def on_close(ws, code, msg):
    print(f"[{now_str()}] [CLOSE] WebSocket ปิดการเชื่อมต่อ: {code}")

def run_ws():
    global ws_app
    while True:
        try:
            ensure_token()
            if not token_info["token"]:
                print(f"[{now_str()}] [ERROR] ไม่สามารถรับ Token ได้ กำลังลองใหม่...")
                time.sleep(5)
                continue

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
            print(f"[{now_str()}] [ERROR] WS loop: {e}")
        time.sleep(5)

def token_refresh_watcher():
    global ws_app
    while True:
        try:
            time.sleep(10)
            if token_info["token"] and time.time() >= (token_info["exp"] - 60):
                fetch_new_token()
                if ws_app:
                    try:
                        ws_app.close()
                    except:
                        pass
        except:
            pass

# --- UI FUNCTIONS ---
def display_all_buses():
    while True:
        try:
            os.system("cls" if os.name == "nt" else "clear")
            print(f"=== ระบบติดตามรถเมล์ มทส. | {now_str()} ===")
            print(f"{'ชื่อรถ':18} {'ตำแหน่ง':50} {'ความเร็ว':8} {'สถานะ':15} {'ที่นั่ง':5}")
            print("-" * 100)

            rows = []
            with state_lock:
                for eid, entity in bus_state.items():
                    lat = get_value(entity, "TIME_SERIES", "latitude")
                    lon = get_value(entity, "TIME_SERIES", "longitude")
                    rows.append({
                        "name": get_value(entity, "ENTITY_FIELD", "name") or "-",
                        "location": get_location_with_bus_stop(lat, lon),
                        "speed": get_value(entity, "TIME_SERIES", "speed") or 0,
                        "status": get_value(entity, "TIME_SERIES", "status") or "-",
                        "seats": get_value(entity, "TIME_SERIES", "availableSeats") or "-",
                    })

            rows.sort(key=lambda x: str(x["name"]))
            for r in rows:
                print(
                    f"{str(r['name'])[:18]:18} "
                    f"{str(r['location'])[:50]:50} "
                    f"{str(r['speed'])[:8]:8} "
                    f"{str(r['status'])[:15]:15} "
                    f"{str(r['seats'])[:5]:5}"
                )
            print("-" * 100)
            print("(กด Ctrl+C เพื่อกลับเมนูหลัก)")
            time.sleep(2)
        except KeyboardInterrupt:
            break

def display_single_bus(bus_name):
    while True:
        try:
            os.system("cls" if os.name == "nt" else "clear")
            print(f"=== ติดตาม: {bus_name} | {now_str()} ===")
            print("-" * 70)

            found = False
            with state_lock:
                for eid, entity in bus_state.items():
                    name = get_value(entity, "ENTITY_FIELD", "name")
                    if name == bus_name:
                        found = True
                        lat = get_value(entity, "TIME_SERIES", "latitude") or "-"
                        lon = get_value(entity, "TIME_SERIES", "longitude") or "-"
                        speed = get_value(entity, "TIME_SERIES", "speed") or "0"
                        status = get_value(entity, "TIME_SERIES", "status") or "-"
                        seats = get_value(entity, "TIME_SERIES", "availableSeats") or "-"
                        location = get_location_with_bus_stop(lat, lon)
                        updated = entity.get("updated_at", "-")

                        print(f"  ชื่อรถ:         {name}")
                        print(f"  ตำแหน่ง:        {location}")
                        print(f"  พิกัด:          {lat}, {lon}")
                        print(f"  ความเร็ว:       {speed} กม./ชม.")
                        print(f"  สถานะ:          {status}")
                        print(f"  ที่นั่งว่าง:     {seats}")
                        print(f"  อัปเดตล่าสุด:   {updated}")
                        break

            if not found:
                print(f"  ไม่พบข้อมูลรถ '{bus_name}'")

            print("-" * 70)
            print("(กด Ctrl+C เพื่อกลับเมนูหลัก)")
            time.sleep(2)
        except KeyboardInterrupt:
            break

def display_route_buses(route_name):
    while True:
        try:
            os.system("cls" if os.name == "nt" else "clear")
            print(f"=== รถบนเส้นทาง: {route_name} | {now_str()} ===")
            print(f"{'ชื่อรถ':18} {'ป้ายที่ใกล้ที่สุด':35} {'ระยะ(ม.)':10} {'ความเร็ว':8} {'ที่นั่ง':5}")
            print("-" * 80)

            buses = get_buses_on_route(route_name)
            if buses:
                for b in buses:
                    print(
                        f"{str(b['name'])[:18]:18} "
                        f"{str(b['nearest_stop'])[:35]:35} "
                        f"{str(b['distance']):10} "
                        f"{str(b['speed'])[:8]:8} "
                        f"{str(b['seats'])[:5]:5}"
                    )
            else:
                print("  ไม่พบรถบนเส้นทางนี้ (อาจอยู่ห่างจากป้ายมากกว่า 300 เมตร)")

            print("-" * 80)
            print("(กด Ctrl+C เพื่อกลับเมนูหลัก)")
            time.sleep(2)
        except KeyboardInterrupt:
            break

def display_stop_buses(stop_name):
    while True:
        try:
            os.system("cls" if os.name == "nt" else "clear")
            print(f"=== รถใกล้ป้าย: {stop_name} | {now_str()} ===")
            print(f"{'ชื่อรถ':18} {'สาย':15} {'ระยะ(ม.)':10} {'ความเร็ว':8} {'สถานะ':15} {'ที่นั่ง':5}")
            print("-" * 75)

            buses = get_buses_near_stop(stop_name)
            if buses:
                for b in buses:
                    print(
                        f"{str(b['name'])[:18]:18} "
                        f"{str(b['route'])[:15]:15} "
                        f"{str(b['distance']):10} "
                        f"{str(b['speed'])[:8]:8} "
                        f"{str(b['status'])[:15]:15} "
                        f"{str(b['seats'])[:5]:5}"
                    )
            else:
                print("  ไม่พบรถใกล้ป้ายนี้ (รัศมี 500 เมตร)")

            print("-" * 75)
            print("(กด Ctrl+C เพื่อกลับเมนูหลัก)")
            time.sleep(2)
        except KeyboardInterrupt:
            break

def main_menu():
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        print("\n" + "=" * 50)
        print("     ระบบติดตามรถเมล์ มทส.")
        print("=" * 50)

        with state_lock:
            bus_count = len(bus_state)
        print(f"\n  รถที่เชื่อมต่อ: {bus_count} คัน")

        print("\n  [1] ดูรถทั้งหมด")
        print("  [2] ดูรถคันเดียว")
        print("  [3] ดูตามสายรถ")
        print("  [4] ดูรถใกล้ป้าย")
        print("  [5] แสดงเส้นทางทั้งหมด")
        print("  [0] ออกจากโปรแกรม")
        print("-" * 50)

        choice = input("\n  เลือก: ").strip()

        if choice == "1":
            display_all_buses()

        elif choice == "2":
            current_buses = []
            with state_lock:
                for eid, entity in bus_state.items():
                    name = get_value(entity, "ENTITY_FIELD", "name")
                    if name and name != "-":
                        current_buses.append(name)
            current_buses.sort()

            print("\n  --- รถที่พบ ---")
            for i, name in enumerate(current_buses, 1):
                print(f"    {i}: {name}")

            if not current_buses:
                print("    ยังไม่มีข้อมูลรถ กรุณารอสักครู่...")
                time.sleep(2)
                continue

            sub = input("\n  เลือกหมายเลข: ").strip()
            if sub.isdigit() and 0 < int(sub) <= len(current_buses):
                display_single_bus(current_buses[int(sub) - 1])

        elif choice == "3":
            print("\n  --- เส้นทางรถเมล์ ---")
            for i, route in enumerate(BUS_STOPS, 1):
                print(f"    {i}: {route['name']} ({len(route['stops'])} ป้าย)")

            sub = input("\n  เลือกหมายเลข: ").strip()
            if sub.isdigit() and 0 < int(sub) <= len(BUS_STOPS):
                display_route_buses(BUS_STOPS[int(sub) - 1]["name"])

        elif choice == "4":
            stop_name = input("\n  พิมพ์ชื่อป้าย (พิมพ์บางส่วนได้): ").strip()
            if stop_name:
                display_stop_buses(stop_name)

        elif choice == "5":
            os.system("cls" if os.name == "nt" else "clear")
            print("\n=== เส้นทางรถเมล์ มทส. ทั้งหมด ===\n")
            for route in BUS_STOPS:
                print(f"  [{route['name']}]")
                for j, stop in enumerate(route["stops"], 1):
                    print(f"    {j}. {stop['name']}")
                print()
            input("  กด Enter เพื่อกลับเมนูหลัก...")

        elif choice == "0":
            print("\n  ออกจากโปรแกรม...")
            break

# --- MAIN ---
if __name__ == "__main__":
    print(f"[{now_str()}] กำลังเริ่มระบบติดตามรถเมล์ มทส....")
    print(f"[{now_str()}] กำลังเชื่อมต่อเซิร์ฟเวอร์...")

    # Start background threads
    threading.Thread(target=run_ws, daemon=True).start()
    threading.Thread(target=token_refresh_watcher, daemon=True).start()

    # Wait for initial data
    print(f"[{now_str()}] กำลังรอข้อมูล...")
    time.sleep(5)

    with state_lock:
        bus_count = len(bus_state)

    if bus_count == 0:
        print(f"[{now_str()}] [WARNING] ยังไม่ได้รับข้อมูล กำลังรอเพิ่มเติม...")
        time.sleep(5)

    with state_lock:
        bus_count = len(bus_state)
    print(f"[{now_str()}] [OK] พบรถ {bus_count} คัน กำลังเปิดเมนู...")

    try:
        main_menu()
    except Exception as e:
        print(f"[{now_str()}] [ERROR] โปรแกรมหยุดทำงาน: {e}")
        import traceback
        traceback.print_exc()