import requests
import websocket
import json
import time
import threading
import socket
import selectors
import math
import base64
from datetime import datetime
from geopy.geocoders import Nominatim


# --- CONFIGURATION ---
BASE_URL = "http://203.158.3.33:8080"
WS_URL = "ws://203.158.3.33:8080/api/ws"
PUBLIC_ID = "44a00910-fa93-11ef-94ed-973314b03447"
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 9000


# --- ป้ายรถเมล์ใน มทส. (6 สาย) ---
BUS_STOPS = [
    {"name": "สายสีเขียว", "stops": [
        {"name": "อาคารเรียนรวม 1", "lat": 14.8822, "lon": 102.0217},
        {"name": "อาคารส่วนกิจการนักศึกษา (หลังใหม่)", "lat": 14.8808, "lon": 102.0192},
        {"name": "หอพักสุรนิเวศ 1", "lat": 14.8786, "lon": 102.0174},
        {"name": "หอพักสุรนิเวศ 15", "lat": 14.8768, "lon": 102.0215},
        {"name": "หอพักสุรนิเวศ 16,18", "lat": 14.8755, "lon": 102.0230},
        {"name": "โรงอาหารกาสะลองคำ", "lat": 14.8780, "lon": 102.0208},
        {"name": "หอพักสุรนิเวศ 7-8,11-12", "lat": 14.8770, "lon": 102.0195},
        {"name": "หอพักสุรนิเวศ 13 B", "lat": 14.8757, "lon": 102.0185},
        {"name": "หอพักสุรนิเวศ 13 A", "lat": 14.8752, "lon": 102.0178},
    ]},
    {"name": "สายสีม่วง", "stops": [
        {"name": "อาคารเรียนรวม 1", "lat": 14.8822, "lon": 102.0217},
        {"name": "อาคารส่วนกิจการนักศึกษา (หลังใหม่)", "lat": 14.8808, "lon": 102.0192},
        {"name": "หอพักสุรนิเวศ 1", "lat": 14.8786, "lon": 102.0174},
        {"name": "หอพักสุรนิเวศ 2,14", "lat": 14.8778, "lon": 102.0163},
        {"name": "หอพักสุรนิเวศ 4-5-6", "lat": 14.8765, "lon": 102.0148},
    ]},
    {"name": "สายสีส้ม", "stops": [
        {"name": "อาคารขนส่ง", "lat": 14.8821, "lon": 102.0249},
        {"name": "อาคารเรียนรวม 2", "lat": 14.8815, "lon": 102.0228},
        {"name": "อาคารบรรณสาร 1", "lat": 14.8803, "lon": 102.0213},
        {"name": "อาคารบรรณสาร 2", "lat": 14.8800, "lon": 102.0205},
        {"name": "อาคารศูนย์เครื่องมือ 1-2-4", "lat": 14.8835, "lon": 102.0180},
        {"name": "อาคารศูนย์เครื่องมือ 3-5-6", "lat": 14.8840, "lon": 102.0170},
        {"name": "อาคารศูนย์เครื่องมือ 9-10,11-12", "lat": 14.8850, "lon": 102.0160},
        {"name": "ครัวท่านท้าว", "lat": 14.8860, "lon": 102.0150},
        {"name": "อาคารส่วนกิจการนักศึกษา (หลังเก่า)", "lat": 14.8815, "lon": 102.0185},
    ]},
    {"name": "สายสีน้ำเงิน", "stops": [
        {"name": "อาคารขนส่ง", "lat": 14.8821, "lon": 102.0249},
        {"name": "สุรสัมมนาคาร", "lat": 14.8930, "lon": 102.0155},
        {"name": "รร.สุรวิวัฒน์", "lat": 14.8850, "lon": 102.0130},
        {"name": "อาคารส่งเสริมสุขภาพ", "lat": 14.8860, "lon": 102.0115},
        {"name": "อาคารศูนย์ความเป็นเลิศ", "lat": 14.8870, "lon": 102.0100},
        {"name": "รพ.มทส.", "lat": 14.8745, "lon": 102.0035},
        {"name": "เทคโนธานี", "lat": 14.8950, "lon": 102.0140},
    ]},
    {"name": "สายสีแดง", "stops": [
        {"name": "อาคารขนส่ง", "lat": 14.8821, "lon": 102.0249},
        {"name": "อาคารเรียนรวม 2", "lat": 14.8815, "lon": 102.0228},
        {"name": "อาคารบรรณสาร 1", "lat": 14.8803, "lon": 102.0213},
        {"name": "อาคารบรรณสาร 2", "lat": 14.8800, "lon": 102.0205},
        {"name": "อาคารศูนย์เครื่องมือ 1-2-4", "lat": 14.8835, "lon": 102.0180},
        {"name": "อาคารศูนย์เครื่องมือ 3-5-6", "lat": 14.8840, "lon": 102.0170},
        {"name": "อาคารศูนย์เครื่องมือ 9-10,11-12", "lat": 14.8850, "lon": 102.0160},
        {"name": "ครัวท่านท้าว", "lat": 14.8860, "lon": 102.0150},
        {"name": "อาคารเรียนรวม 1", "lat": 14.8822, "lon": 102.0217},
        {"name": "อาคารส่วนกิจการนักศึกษา (หลังใหม่)", "lat": 14.8808, "lon": 102.0192},
        {"name": "หอพักสุรนิเวศ 15", "lat": 14.8768, "lon": 102.0215},
        {"name": "หอพักสุรนิเวศ 16,18", "lat": 14.8755, "lon": 102.0230},
        {"name": "โรงอาหารกาสะลองคำ", "lat": 14.8780, "lon": 102.0208},
        {"name": "หอพักสุรนิเวศ 7-8,11-12", "lat": 14.8770, "lon": 102.0195},
        {"name": "หอพักสุรนิเวศ 13 B", "lat": 14.8757, "lon": 102.0185},
        {"name": "หอพักสุรนิเวศ 13 A", "lat": 14.8752, "lon": 102.0178},
        {"name": "หอพักสุรนิเวศ 1", "lat": 14.8786, "lon": 102.0174},
        {"name": "หอพักสุรนิเวศ 2,14", "lat": 14.8778, "lon": 102.0163},
        {"name": "หอพักสุรนิเวศ 4-5-6", "lat": 14.8765, "lon": 102.0148},
    ]},
    {"name": "สายสีเหลือง", "stops": [
        {"name": "ตลาดหน้า มทส.ประตู 1", "lat": 14.8970, "lon": 102.0250},
        {"name": "หอพักสุรนิเวศ 15", "lat": 14.8768, "lon": 102.0215},
        {"name": "หอพักสุรนิเวศ 16,18", "lat": 14.8755, "lon": 102.0230},
        {"name": "โรงอาหารกาสะลองคำ", "lat": 14.8780, "lon": 102.0208},
        {"name": "หอพักสุรนิเวศ 7-8,11-12", "lat": 14.8770, "lon": 102.0195},
        {"name": "หอพักสุรนิเวศ 13 B", "lat": 14.8757, "lon": 102.0185},
        {"name": "หอพักสุรนิเวศ 13 A", "lat": 14.8752, "lon": 102.0178},
        {"name": "หอพักสุรนิเวศ 1", "lat": 14.8786, "lon": 102.0174},
        {"name": "หอพักสุรนิเวศ 2,14", "lat": 14.8778, "lon": 102.0163},
        {"name": "หอพักสุรนิเวศ 4-5-6", "lat": 14.8765, "lon": 102.0148},
    ]},
]


# --- ตัวแปรระบบ ---
sel = selectors.DefaultSelector()
bus_state = {}
state_lock = threading.Lock()
location_cache = {}
location_lock = threading.Lock()
token_info = {"token": None, "exp": 0}


# =====================================================================
# ส่วนที่ 1: จัดการ Token
# =====================================================================

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def decode_jwt_exp(token):
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return 0
        payload = parts[1]
        padding = "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload + padding)
        obj = json.loads(decoded.decode("utf-8"))
        return int(obj.get("exp", 0))
    except Exception:
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
        if token_info["exp"]:
            exp_text = datetime.fromtimestamp(token_info["exp"]).strftime("%Y-%m-%d %H:%M:%S")
        else:
            exp_text = "ไม่ทราบ"
        print(f"[{now_str()}] [Token] ต่ออายุสำเร็จ หมดอายุ={exp_text}")
    except Exception as e:
        print(f"[{now_str()}] [Token] ผิดพลาด: {e}")


def ensure_token():
    if not token_info["token"] or time.time() >= (token_info["exp"] - 60):
        fetch_new_token()


def token_refresh_watcher():
    """ตรวจสอบ Token ทุก 10 วินาที ถ้าใกล้หมดอายุจะต่ออายุอัตโนมัติ"""
    while True:
        try:
            time.sleep(10)
            if token_info["token"] and time.time() >= (token_info["exp"] - 60):
                print(f"[{now_str()}] [Token] ใกล้หมดอายุ กำลังต่ออายุ...")
                fetch_new_token()
        except Exception as e:
            print(f"[{now_str()}] [Token] ผิดพลาดในการตรวจสอบ: {e}")


# =====================================================================
# ส่วนที่ 2: แปลงพิกัดเป็นชื่อสถานที่
# =====================================================================

def calculate_distance(lat1, lon1, lat2, lon2):
    try:
        return math.sqrt((float(lat1) - lat2)**2 + (float(lon1) - lon2)**2) * 111319
    except Exception:
        return 9999


def get_location_name(lat, lon):
    """แปลงพิกัดเป็นชื่อสถานที่ - ตรวจป้ายรถเมล์ก่อน แล้วดูจาก cache"""
    if lat is None or lon is None or lat == "-" or lon == "-":
        return "-"
    try:
        curr_lat = float(lat)
        curr_lon = float(lon)

        # ตรวจสอบป้ายรถเมล์ (รัศมี 10 เมตร)
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

        # ดูจาก cache
        cache_key = (round(curr_lat, 4), round(curr_lon, 4))
        with location_lock:
            if cache_key in location_cache:
                return location_cache[cache_key]

        # เรียก Geopy ใน background ไม่ block
        threading.Thread(
            target=_resolve_geopy,
            args=(lat, lon, cache_key),
            daemon=True
        ).start()
        return "ภายใน มทส."
    except Exception:
        return "มทส."


def _resolve_geopy(lat, lon, cache_key):
    """เรียก Geopy ใน background thread"""
    try:
        geolocator = Nominatim(user_agent="sut_bus_server_v2")
        location = geolocator.reverse(f"{lat}, {lon}", language="th", timeout=10)
        if location:
            raw = location.raw.get("address", {})
            place = (
                raw.get("amenity")
                or raw.get("building")
                or raw.get("tourism")
                or raw.get("highway")
                or raw.get("suburb")
                or raw.get("village")
                or "มทส."
            )
            with location_lock:
                location_cache[cache_key] = place
    except Exception:
        pass


# =====================================================================
# ส่วนที่ 3: รับข้อมูลจาก WebSocket ของ มทส.
# =====================================================================

def get_data_from_server():
    """เชื่อมต่อครั้งเดียว แล้วส่ง GET_BUS ซ้ำผ่าน socket เดิม"""
    global local_bus_state
    while not task_completed.is_set():
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(SERVER_ADDR)
            # เชื่อมต่อสำเร็จ - ใช้ท่อเดิมวนซ้ำ
            while not task_completed.is_set():
                sock.sendall(b"GET_BUS")

                # รับข้อมูลจนเจอ \n (จบ 1 ชุด)
                buf = b""
                while b"\n" not in buf:
                    chunk = sock.recv(65536)
                    if not chunk:
                        raise ConnectionError("Server ปิด")
                    buf += chunk

                line = buf.split(b"\n")[0]
                local_bus_state = json.loads(line.decode("utf-8"))
                time.sleep(1)

        except Exception as e:
            print(f"[ผิดพลาด] {e} - เชื่อมต่อใหม่ใน 3 วินาที...")
        finally:
            if sock:
                try:
                    sock.close()
                except:
                    pass
        time.sleep(3)
        

def get_value(entity, section, key):
    return entity.get(section, {}).get(key, {}).get("value")


def merge_entity(item):
    entity_id = item["entityId"]["id"]
    with state_lock:
        if entity_id not in bus_state:
            bus_state[entity_id] = {
                "ENTITY_FIELD": {},
                "ATTRIBUTE": {},
                "TIME_SERIES": {},
                "updated_at": None,
            }
        latest = item.get("latest", {})
        for sec in ["ENTITY_FIELD", "ATTRIBUTE", "TIME_SERIES"]:
            if sec in latest:
                bus_state[entity_id][sec].update(latest[sec])
        bus_state[entity_id]["updated_at"] = now_str()


def on_ws_message(ws, message):
    try:
        msg = json.loads(message)
        if msg.get("errorCode", 0) != 0:
            print(f"[{now_str()}] [WebSocket] ข้อผิดพลาด: {msg.get('errorMsg')}")
            return

        # ข้อมูลเริ่มต้น
        data_section = msg.get("data")
        if data_section and data_section.get("data"):
            for item in data_section["data"]:
                merge_entity(item)

        # ข้อมูลอัปเดต
        update_section = msg.get("update")
        if update_section:
            for item in update_section:
                merge_entity(item)
    except Exception as e:
        print(f"[{now_str()}] [WebSocket] แปลงข้อมูลผิดพลาด: {e}")


def on_ws_open(ws):
    print(f"[{now_str()}] [WebSocket] เชื่อมต่อสำเร็จ")
    ensure_token()

    ws.send(json.dumps({
        "authCmd": {"cmdId": 0, "token": token_info["token"]}
    }))

    keys = [
        {"type": "TIME_SERIES", "key": "latitude"},
        {"type": "TIME_SERIES", "key": "longitude"},
        {"type": "TIME_SERIES", "key": "speed"},
        {"type": "TIME_SERIES", "key": "status"},
        {"type": "TIME_SERIES", "key": "availableSeats"},
    ]

    ws.send(json.dumps({
        "cmds": [{
            "type": "ENTITY_DATA",
            "query": {
                "entityFilter": {
                    "type": "deviceType",
                    "resolveMultiple": True,
                    "deviceTypes": ["bus"],
                    "deviceNameFilter": "",
                },
                "pageLink": {"page": 0, "pageSize": 100, "dynamic": True},
                "entityFields": [
                    {"type": "ENTITY_FIELD", "key": "name"},
                    {"type": "ENTITY_FIELD", "key": "label"},
                ],
                "latestValues": keys,
            },
            "latestCmd": {"keys": keys},
            "cmdId": 1,
        }]
    }))
    print(f"[{now_str()}] [WebSocket] สมัครรับข้อมูลสำเร็จ")


def on_ws_error(ws, error):
    print(f"[{now_str()}] [WebSocket] ผิดพลาด: {error}")


def on_ws_close(ws, code, msg):
    print(f"[{now_str()}] [WebSocket] ปิดการเชื่อมต่อ code={code}")


def run_websocket_forever():
    """เชื่อมต่อ WebSocket วนซ้ำ ถ้าหลุดจะเชื่อมต่อใหม่"""
    while True:
        try:
            ensure_token()
            print(f"[{now_str()}] [WebSocket] กำลังเชื่อมต่อ...")
            ws = websocket.WebSocketApp(
                WS_URL,
                header={"Origin": BASE_URL},
                on_open=on_ws_open,
                on_message=on_ws_message,
                on_error=on_ws_error,
                on_close=on_ws_close,
            )
            ws.run_forever(ping_interval=20, ping_timeout=10)
        except Exception as e:
            print(f"[{now_str()}] [WebSocket] เชื่อมต่อล้มเหลว: {e}")
        print(f"[{now_str()}] [WebSocket] เชื่อมต่อใหม่ใน 5 วินาที...")
        time.sleep(5)


# =====================================================================
# ส่วนที่ 4: สร้างข้อมูลพร้อมส่งให้ Client
# =====================================================================

def build_client_data():
    """สร้าง dict ที่ประมวลผลเสร็จแล้ว พร้อมส่งให้ Client เลย"""
    result = {}
    with state_lock:
        for eid, entity in bus_state.items():
            lat = get_value(entity, "TIME_SERIES", "latitude")
            lon = get_value(entity, "TIME_SERIES", "longitude")
            result[eid] = {
                "name": get_value(entity, "ENTITY_FIELD", "name") or "-",
                "latitude": lat or "-",
                "longitude": lon or "-",
                "location": get_location_name(lat, lon),
                "speed": get_value(entity, "TIME_SERIES", "speed") or "0",
                "status": get_value(entity, "TIME_SERIES", "status") or "-",
                "seats": get_value(entity, "TIME_SERIES", "availableSeats") or "-",
                "updated_at": entity.get("updated_at", "-"),
            }
    return result


# =====================================================================
# ส่วนที่ 5: TCP Server (Persistent Connection)
# =====================================================================

def accept_wrapper(sock, mask):
    conn, addr = sock.accept()
    print(f"[{now_str()}] [TCP] Client เชื่อมต่อ: {addr}")
    conn.setblocking(False)
    sel.register(conn, selectors.EVENT_READ, read_wrapper)


def read_wrapper(conn, mask):
    try:
        data = conn.recv(1024)
        if data:
            cmd = data.decode().strip().upper()

            if cmd == "GET_BUS":
                client_data = build_client_data()
                response = json.dumps(client_data, ensure_ascii=False) + "\n"
                conn.sendall(response.encode("utf-8"))

            elif cmd == "GET_STOPS":
                response = json.dumps(BUS_STOPS, ensure_ascii=False) + "\n"
                conn.sendall(response.encode("utf-8"))

            elif cmd == "QUIT":
                print(f"[{now_str()}] [TCP] Client ขอตัดการเชื่อมต่อ")
                sel.unregister(conn)
                conn.close()

            # คำสั่งอื่น -> ไม่ปิด connection
            # Client ส่งคำสั่งถัดไปผ่านท่อเดิมได้เลย

        else:
            # data ว่าง = Client ปิด socket ฝั่งตัวเอง
            print(f"[{now_str()}] [TCP] Client ตัดการเชื่อมต่อ")
            sel.unregister(conn)
            conn.close()
    except Exception:
        try:
            sel.unregister(conn)
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


# =====================================================================
# ส่วนที่ 6: แสดงผลบน Server (สำหรับ debug)
# =====================================================================

def server_display_thread():
    """แสดงผลบนหน้าจอ Server เพื่อตรวจสอบ"""
    while True:
        time.sleep(5)
        with state_lock:
            count = len(bus_state)
        if count > 0:
            print(f"[{now_str()}] [สถานะ] กำลังติดตามรถ {count} คัน")


# =====================================================================
# จุดเริ่มต้น
# =====================================================================

if __name__ == "__main__":
    print(f"[{now_str()}] [เริ่มต้น] ระบบ Server ติดตามรถเมล์ มทส.")
    print(f"[{now_str()}] [เริ่มต้น] TCP Server ที่ {SERVER_HOST}:{SERVER_PORT}")
    print(f"[{now_str()}] [เริ่มต้น] คำสั่งที่รับ: GET_BUS, GET_STOPS, QUIT")
    print("-" * 60)

    # เปิด TCP Server
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((SERVER_HOST, SERVER_PORT))
    server_sock.listen()
    server_sock.setblocking(False)
    sel.register(server_sock, selectors.EVENT_READ, accept_wrapper)

    # เริ่ม Thread ต่างๆ
    threading.Thread(target=run_websocket_forever, daemon=True).start()
    threading.Thread(target=token_refresh_watcher, daemon=True).start()
    threading.Thread(target=server_display_thread, daemon=True).start()

    print(f"[{now_str()}] [TCP] Server พร้อมรับการเชื่อมต่อ")

    # วนรับ Event จาก Client
    while True:
        events = sel.select(timeout=1)
        for key, mask in events:
            key.data(key.fileobj, mask)