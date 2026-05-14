import requests, websocket, json, time, threading, os, base64, math, smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CONFIGURATION ---
BASE_URL = "http://203.158.3.33:8080"
WS_URL = "ws://203.158.3.33:8080/api/ws"
PUBLIC_ID = "44a00910-fa93-11ef-94ed-973314b03447"

SMTP_CONFIG = {
    "server": "smtp.gmail.com",
    "port": 587,
    "email": "sutnewbus.send@gmail.com",
    "password": "ucki eult ftjq mddn" 
}

# ฐานข้อมูลสถานที่สำคัญ
SUT_LOCATIONS = [
    {"name": "หอพักหญิง S1-S6", "lat": 14.8765, "lon": 102.0165},
    {"name": "หอพักชาย S7-S12", "lat": 14.8752, "lon": 102.0188},
    {"name": "หอพักหญิง S15", "lat": 14.8768, "lon": 102.0215},
    {"name": "อาคารเรียนรวม 1 (B1)", "lat": 14.8824, "lon": 102.0205},
    {"name": "อาคารเรียนรวม 2 (B2)", "lat": 14.8812, "lon": 102.0209},
    {"name": "ศูนย์บรรณสาร (ห้องสมุด)", "lat": 14.8795, "lon": 102.0198},
    {"name": "อาคารบริหาร (AD)", "lat": 14.8818, "lon": 102.0175},
    {"name": "เทคโนธานี", "lat": 14.8963, "lon": 102.0124},
]

# --- STATE ---
bus_state = {}
state_lock = threading.Lock()
token_info = {"token": None, "exp": 0}
target_bus_id = None
user_email = ""
email_submitted = threading.Event() # เช็คว่าพิมพ์เมลเสร็จหรือยัง
task_completed = threading.Event()

# --- FUNCTIONS ---
def calculate_distance(lat1, lon1, lat2, lon2):
    try: return math.sqrt((float(lat1) - lat2)**2 + (float(lon1) - lon2)**2) * 111319
    except: return 9999

def get_place_name(lat, lon):
    if not lat or not lon or lat == 0: return "กำลังระบุตำแหน่ง..."
    try:
        curr_lat, curr_lon = float(lat), float(lon)
        for loc in SUT_LOCATIONS:
            if calculate_distance(curr_lat, curr_lon, loc["lat"], loc["lon"]) < 200:
                return loc["name"]
        return "ภายใน มทส."
    except: return "ไม่ทราบตำแหน่ง"

def send_notification(bus_name, stop_name):
    if not user_email or user_email.lower() == 'n': 
        task_completed.set()
        return
    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_CONFIG["email"]
        msg["To"] = user_email
        msg["Subject"] = f"[แจ้งเตือน] {bus_name} ถึง {stop_name} แล้ว"
        body = f"ขณะนี้ {bus_name} ถึง {stop_name} เรียบร้อยแล้ว\nเวลา: {datetime.now().strftime('%H:%M:%S')}"
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP(SMTP_CONFIG["server"], SMTP_CONFIG["port"]) as server:
            server.starttls()
            server.login(SMTP_CONFIG["email"], SMTP_CONFIG["password"])
            server.send_message(msg)
        task_completed.set()
    except: task_completed.set()

def print_single_bus_view():
    """หน้าจอติดตามที่จะอัปเดตตลอดเวลาแม้กำลังพิมพ์เมล"""
    while not task_completed.is_set():
        with state_lock:
            bus = bus_state.get(target_bus_id)
        
        if bus and bus.get("lat") != 0:
            os.system("cls" if os.name == "nt" else "clear")
            now = datetime.now().strftime("%H:%M:%S")
            print(f"--- Tracking: {bus['name']} | {now} ---")
            print("=" * 110)
            print(f"{'NAME':20} {'LOCATION (SUT)':35} {'STATUS':18} {'SEATS LEFT':10}")
            print("-" * 110)
            
            place = get_place_name(bus.get("lat"), bus.get("lon"))
            print(f"{bus['name']:20} {place:35} {bus.get('status', 'On route'):18} {bus.get('seats', '40'):10}")
            print("=" * 110)
            
            if not email_submitted.is_set():
                print(f"[ระบบ] กรุณาพิมพ์อีเมลด้านล่างเพื่อรับแจ้งเตือน (หรือพิมพ์ 'n' เพื่อข้าม)")
                print(f">>> อีเมล: {user_email}", end="\r") # แสดงสิ่งที่กำลังพิมพ์
            else:
                print(f"[ระบบ] สถานะแจ้งเตือน: {user_email if user_email != 'n' else 'ปิดการแจ้งเตือน'}")
                print(f"[ระบบ] กำลังเฝ้าติดตามจนกว่าจะถึงป้าย...")
        
        time.sleep(1)

def on_message(ws, message):
    try:
        msg = json.loads(message)
        data = msg.get("data", {}).get("data") or msg.get("update")
        if data:
            with state_lock:
                for item in data:
                    eid = item["entityId"]["id"]
                    if eid not in bus_state: 
                        bus_state[eid] = {"name": "-", "lat": 0, "lon": 0, "status": "-", "seats": "-"}
                    latest = item.get("latest", {})
                    if "ENTITY_FIELD" in latest:
                        bus_state[eid]["name"] = latest["ENTITY_FIELD"].get("name", {}).get("value", "-")
                    if "TIME_SERIES" in latest:
                        ts = latest["TIME_SERIES"]
                        if "latitude" in ts: bus_state[eid]["lat"] = ts["latitude"].get("value")
                        if "longitude" in ts: bus_state[eid]["lon"] = ts["longitude"].get("value")
                        if "status" in ts: bus_state[eid]["status"] = ts["status"].get("value")
                        if "availableSeats" in ts: bus_state[eid]["seats"] = ts["availableSeats"].get("value")
                    
                    if eid == target_bus_id and not task_completed.is_set():
                        # ตรวจสอบรัศมี 30 เมตรเพื่อส่งเมล
                        for loc in SUT_LOCATIONS:
                            if calculate_distance(bus_state[eid]["lat"], bus_state[eid]["lon"], loc["lat"], loc["lon"]) < 30:
                                send_notification(bus_state[eid]["name"], loc["name"])
                                break
    except: pass

def run_ws():
    def on_open(ws):
        ws.send(json.dumps({"authCmd": {"cmdId": 0, "token": token_info["token"]}}))
        keys = [{"type": "TIME_SERIES", "key": k} for k in ["latitude", "longitude", "status", "availableSeats"]]
        sub = {"cmds": [{"type": "ENTITY_DATA", "query": {"entityFilter": {"type": "deviceType", "resolveMultiple": True, "deviceTypes": ["bus"]},
               "pageLink": {"page": 0, "pageSize": 100}, "entityFields": [{"type": "ENTITY_FIELD", "key": "name"}], "latestValues": keys}, "cmdId": 1}]}
        ws.send(json.dumps(sub))
    ws = websocket.WebSocketApp(WS_URL, header={"Origin": BASE_URL}, on_open=on_open, on_message=on_message)
    ws.run_forever()

if __name__ == "__main__":
    r = requests.post(f"{BASE_URL}/api/auth/login/public", json={"publicId": PUBLIC_ID})
    token_info["token"] = r.json()["token"]
    threading.Thread(target=run_ws, daemon=True).start()
    
    print("กำลังโหลดรายชื่อรถเมล์...")
    time.sleep(3)

    os.system("cls" if os.name == "nt" else "clear")
    print("=== เลือกคันที่ต้องการติดตามเจาะจง ===")
    buses = []
    with state_lock:
        for eid, info in bus_state.items():
            if info["name"] != "-": buses.append({"id": eid, "name": info["name"]})
    
    buses.sort(key=lambda x: x["name"])
    for i, b in enumerate(buses, 1):
        print(f"{i}: {b['name']}")
    
    choice = int(input("\nกรอกหมายเลขรถที่ต้องการติดตาม: "))
    target_bus_id = buses[choice-1]["id"]

    # เริ่มหน้าจอ Tracking ทันที
    threading.Thread(target=print_single_bus_view, daemon=True).start()

    # รับอีเมลแบบไม่ขวางการทำงาน
    user_email = input().strip()
    email_submitted.set()
    
    while not task_completed.is_set():
        time.sleep(1)
    
    print(f"\n[เสร็จสิ้น] ระบบแจ้งเตือนเรียบร้อยแล้ว")