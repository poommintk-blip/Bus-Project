#!/usr/bin/env python3
"""
SUT Bus Tracker - ระบบติดตามรถเมล์แบบเรียลไทม์
มหาวิทยาลัยเทคโนโลยีสุรนารี (มทส.)

คุณสมบัติ:
- ติดตามรถเมล์ มทส. ทุกคันแบบเรียลไทม์ผ่าน WebSocket
- เมนูโต้ตอบเลือกรถเมล์ที่ต้องการติดตามเฉพาะคัน
- แจ้งเตือนผ่านอีเมลเมื่อรถเมล์ถึงป้าย/ออกจากป้าย
- ระบบป้องกันการแจ้งเตือนซ้ำ (Hysteresis + Cooldown)
"""

import requests
import websocket
import json
import time
import threading
import os
import base64
import math
import smtplib
import logging
import queue
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dataclasses import dataclass
from typing import Optional, Dict, Set


# ==============================================================================
# ตั้งค่าระบบ LOG
# ==============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bus_tracker.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger("bus_tracker")


# ==============================================================================
# การตั้งค่าระบบ
# ==============================================================================
@dataclass
class TrackerConfig:
    base_url: str = os.getenv("BASE_URL", "http://203.158.3.33:8080")
    ws_url: str = os.getenv("WS_URL", "ws://203.158.3.33:8080/api/ws")
    public_id: str = os.getenv(
        "PUBLIC_ID", "44a00910-fa93-11ef-94ed-973314b03447"
    )

    # อีเมล
    smtp_server: str = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    sender_email: str = os.getenv("SENDER_EMAIL", "")
    sender_password: str = os.getenv("SENDER_PASSWORD", "")
    recipient_email: str = os.getenv("RECIPIENT_EMAIL", "")

    # ระยะทาง (เมตร)
    arrival_radius: float = 30.0
    departure_radius: float = 50.0
    place_name_radius: float = 100.0

    # เวลา
    notification_cooldown: int = 120
    ping_interval: int = 30
    ping_timeout: int = 10
    token_refresh_margin: int = 120
    reconnect_delay: int = 5


CONFIG = TrackerConfig()


# ==============================================================================
# สถานที่สำคัญใน มทส.
# ==============================================================================
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


# ==============================================================================
# ป้ายรถเมล์ (6 สาย)
# ==============================================================================
BUS_STOPS = [
    {"name": "สายสีเขียว", "stops": [
        {"name": "อาคารเรียนรวม 1", "lat": 14.8822, "lon": 102.0217},
        {"name": "อาคารส่วนกิจการนักศึกษา (หลังใหม่)",
         "lat": 14.8808, "lon": 102.0192},
        {"name": "หอพักสุรนิเวศ 1", "lat": 14.8786, "lon": 102.0174},
        {"name": "หอพักสุรนิเวศ 15", "lat": 14.8768, "lon": 102.0215},
        {"name": "หอพักสุรนิเวศ 16,18", "lat": 14.8755, "lon": 102.0230},
        {"name": "โรงอาหารกาสะลองคำ", "lat": 14.8780, "lon": 102.0208},
        {"name": "หอพักสุรนิเวศ 7-8,11-12",
         "lat": 14.8770, "lon": 102.0195},
        {"name": "หอพักสุรนิเวศ 13 B", "lat": 14.8757, "lon": 102.0185},
        {"name": "หอพักสุรนิเวศ 13 A", "lat": 14.8752, "lon": 102.0178},
    ]},
    {"name": "สายสีม่วง", "stops": [
        {"name": "อาคารเรียนรวม 1", "lat": 14.8822, "lon": 102.0217},
        {"name": "อาคารส่วนกิจการนักศึกษา (หลังใหม่)",
         "lat": 14.8808, "lon": 102.0192},
        {"name": "หอพักสุรนิเวศ 1", "lat": 14.8786, "lon": 102.0174},
        {"name": "หอพักสุรนิเวศ 2,14", "lat": 14.8778, "lon": 102.0163},
        {"name": "หอพักสุรนิเวศ 4-5-6", "lat": 14.8765, "lon": 102.0148},
    ]},
    {"name": "สายสีส้ม", "stops": [
        {"name": "อาคารขนส่ง", "lat": 14.8821, "lon": 102.0249},
        {"name": "อาคารเรียนรวม 2", "lat": 14.8815, "lon": 102.0228},
        {"name": "อาคารบรรณสาร 1", "lat": 14.8803, "lon": 102.0213},
        {"name": "อาคารบรรณสาร 2", "lat": 14.8800, "lon": 102.0205},
        {"name": "อาคารศูนย์เครื่องมือ 1-2-4",
         "lat": 14.8835, "lon": 102.0180},
        {"name": "อาคารศูนย์เครื่องมือ 3-5-6",
         "lat": 14.8840, "lon": 102.0170},
        {"name": "อาคารศูนย์เครื่องมือ 9-10,11-12",
         "lat": 14.8850, "lon": 102.0160},
        {"name": "ครัวท่านท้าว", "lat": 14.8860, "lon": 102.0150},
        {"name": "อาคารส่วนกิจการนักศึกษา (หลังเก่า)",
         "lat": 14.8815, "lon": 102.0185},
    ]},
    {"name": "สายสีน้ำเงิน", "stops": [
        {"name": "อาคารขนส่ง", "lat": 14.8821, "lon": 102.0249},
        {"name": "สุรสัมมนาคาร", "lat": 14.8930, "lon": 102.0155},
        {"name": "รร.สุรวิวัฒน์", "lat": 14.8850, "lon": 102.0130},
        {"name": "อาคารส่งเสริมสุขภาพ", "lat": 14.8860, "lon": 102.0115},
        {"name": "อาคารศูนย์ความเป็นเลิศ",
         "lat": 14.8870, "lon": 102.0100},
        {"name": "รพ.มทส.", "lat": 14.8745, "lon": 102.0035},
        {"name": "เทคโนธานี", "lat": 14.8950, "lon": 102.0140},
    ]},
    {"name": "สายสีแดง", "stops": [
        {"name": "อาคารขนส่ง", "lat": 14.8821, "lon": 102.0249},
        {"name": "อาคารเรียนรวม 2", "lat": 14.8815, "lon": 102.0228},
        {"name": "อาคารบรรณสาร 1", "lat": 14.8803, "lon": 102.0213},
        {"name": "อาคารบรรณสาร 2", "lat": 14.8800, "lon": 102.0205},
        {"name": "อาคารศูนย์เครื่องมือ 1-2-4",
         "lat": 14.8835, "lon": 102.0180},
        {"name": "อาคารศูนย์เครื่องมือ 3-5-6",
         "lat": 14.8840, "lon": 102.0170},
        {"name": "อาคารศูนย์เครื่องมือ 9-10,11-12",
         "lat": 14.8850, "lon": 102.0160},
        {"name": "ครัวท่านท้าว", "lat": 14.8860, "lon": 102.0150},
        {"name": "อาคารเรียนรวม 1", "lat": 14.8822, "lon": 102.0217},
        {"name": "อาคารส่วนกิจการนักศึกษา (หลังใหม่)",
         "lat": 14.8808, "lon": 102.0192},
        {"name": "หอพักสุรนิเวศ 15", "lat": 14.8768, "lon": 102.0215},
        {"name": "หอพักสุรนิเวศ 16,18", "lat": 14.8755, "lon": 102.0230},
        {"name": "โรงอาหารกาสะลองคำ", "lat": 14.8780, "lon": 102.0208},
        {"name": "หอพักสุรนิเวศ 7-8,11-12",
         "lat": 14.8770, "lon": 102.0195},
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
        {"name": "หอพักสุรนิเวศ 7-8,11-12",
         "lat": 14.8770, "lon": 102.0195},
        {"name": "หอพักสุรนิเวศ 13 B", "lat": 14.8757, "lon": 102.0185},
        {"name": "หอพักสุรนิเวศ 13 A", "lat": 14.8752, "lon": 102.0178},
        {"name": "หอพักสุรนิเวศ 1", "lat": 14.8786, "lon": 102.0174},
        {"name": "หอพักสุรนิเวศ 2,14", "lat": 14.8778, "lon": 102.0163},
        {"name": "หอพักสุรนิเวศ 4-5-6", "lat": 14.8765, "lon": 102.0148},
    ]},
]


# ==============================================================================
# จัดการสถานะระบบ
# ==============================================================================
bus_state: Dict[str, dict] = {}
bus_stop_status: Dict[str, Dict[str, str]] = {}
bus_stop_cooldown: Dict[tuple, float] = {}
state_lock = threading.Lock()
ws_lock = threading.Lock()
token_info = {"token": None, "exp": 0}
ws_app = None
email_queue: queue.Queue = queue.Queue()

# --- การเลือกของผู้ใช้ ---
monitored_bus_ids: Set[str] = set()
email_bus_ids: Set[str] = set()
monitor_all: bool = True
selection_lock = threading.Lock()

# ป้องกันไม่ให้ตารางแสดงทับเมนู
menu_active = threading.Event()


# ==============================================================================
# ฟังก์ชันทั่วไป
# ==============================================================================
def calculate_distance(lat1, lon1, lat2, lon2) -> float:
    """สูตร Haversine - คืนค่าระยะทางเป็นเมตร"""
    try:
        R = 6371000
        phi1 = math.radians(float(lat1))
        phi2 = math.radians(float(lat2))
        d_phi = math.radians(float(lat2) - float(lat1))
        d_lambda = math.radians(float(lon2) - float(lon1))

        a = (math.sin(d_phi / 2) ** 2 +
             math.cos(phi1) * math.cos(phi2) *
             math.sin(d_lambda / 2) ** 2)
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    except (ValueError, TypeError):
        return 9999.0


def decode_jwt_exp(token: str) -> int:
    """ถอดรหัส JWT และดึงเวลาหมดอายุ"""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("รูปแบบ JWT ไม่ถูกต้อง: ต้องมี 3 ส่วน")
        payload = parts[1]
        padding = "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload + padding)
        obj = json.loads(decoded.decode("utf-8"))
        exp = int(obj.get("exp", 0))
        if exp == 0:
            raise ValueError("ไม่พบ 'exp' ใน JWT")
        return exp
    except Exception as e:
        logger.error("ถอดรหัส JWT ล้มเหลว: %s", e)
        return 0


def get_place_name(lat, lon) -> str:
    """ค้นหาชื่อสถานที่ใน มทส. ที่ใกล้ที่สุด"""
    if lat == "-" or lon == "-" or lat is None or lon is None:
        return "-"
    try:
        curr_lat, curr_lon = float(lat), float(lon)
        best_name = "บนเส้นทาง"
        best_dist = CONFIG.place_name_radius

        for loc in SUT_LOCATIONS:
            dist = calculate_distance(
                curr_lat, curr_lon, loc["lat"], loc["lon"]
            )
            if dist < best_dist:
                best_dist = dist
                best_name = loc["name"]

        return best_name
    except (ValueError, TypeError):
        return "กำลังระบุตำแหน่ง..."


def get_entity_value(entity: dict, section: str, key: str):
    """ดึงค่าจาก bus_state entity อย่างปลอดภัย"""
    return entity.get(section, {}).get(key, {}).get("value")


# ==============================================================================
# ระบบอีเมล
# ==============================================================================
def send_email_impl(subject: str, body: str):
    """ส่งอีเมลผ่าน SMTP"""
    if not CONFIG.sender_email or not CONFIG.sender_password:
        logger.warning("ยังไม่ได้ตั้งค่าอีเมล - ข้าม: %s", subject)
        return

    try:
        msg = MIMEMultipart()
        msg["From"] = CONFIG.sender_email
        msg["To"] = CONFIG.recipient_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP(CONFIG.smtp_server, CONFIG.smtp_port) as server:
            server.starttls()
            server.login(CONFIG.sender_email, CONFIG.sender_password)
            server.send_message(msg)

        logger.info("[อีเมล] ส่งสำเร็จ: %s", subject)
    except Exception as e:
        logger.error("[อีเมล ผิดพลาด] %s", e)


def queue_email(subject: str, body: str):
    """เพิ่มอีเมลเข้าคิว (ไม่บล็อก)"""
    email_queue.put((subject, body))


def email_worker():
    """เธรดพื้นหลัง - ส่งอีเมลจากคิว"""
    while True:
        try:
            subject, body = email_queue.get()
            send_email_impl(subject, body)
        except Exception as e:
            logger.error("[อีเมล Worker ผิดพลาด] %s", e)
        finally:
            email_queue.task_done()


# ==============================================================================
# ตรวจจับรถเมล์ที่ป้าย (พร้อม Hysteresis + Cooldown)
# ==============================================================================
def check_bus_at_stop(bus_id: str, bus_name: str, lat, lon):
    """ตรวจสอบว่ารถเมล์อยู่ที่ป้ายหรือไม่ ส่งอีเมลเฉพาะคันที่เลือกไว้"""
    try:
        if lat == "-" or lon == "-" or lat is None or lon is None:
            return
        curr_lat, curr_lon = float(lat), float(lon)
    except (ValueError, TypeError):
        return

    # ตรวจสอบว่ารถคันนี้เปิดแจ้งเตือนอีเมลไว้หรือไม่
    with selection_lock:
        should_email = bus_id in email_bus_ids

    if not should_email:
        return

    with state_lock:
        if bus_id not in bus_stop_status:
            bus_stop_status[bus_id] = {}

        currently_near: Set[str] = set()

        # --- ตรวจสอบการเข้าจอดป้ายทุกป้าย ---
        for bus_route in BUS_STOPS:
            route_name = bus_route["name"]
            for stop in bus_route["stops"]:
                dist = calculate_distance(
                    curr_lat, curr_lon, stop["lat"], stop["lon"]
                )

                if dist < CONFIG.arrival_radius:
                    stop_name = stop["name"]
                    currently_near.add(stop_name)
                    old_status = bus_stop_status[bus_id].get(stop_name)

                    if old_status != "arrived":
                        cooldown_key = (bus_id, stop_name)
                        last_sent = bus_stop_cooldown.get(cooldown_key, 0)

                        if (time.time() - last_sent
                                > CONFIG.notification_cooldown):
                            bus_stop_status[bus_id][stop_name] = "arrived"
                            bus_stop_cooldown[cooldown_key] = time.time()

                            timestamp = datetime.now().strftime(
                                "%Y-%m-%d %H:%M:%S"
                            )
                            subject = (
                                f"[รถถึงป้าย] {bus_name} "
                                f"ถึง {stop_name}"
                            )
                            body = _build_email_body(
                                "แจ้งเตือนรถเมล์ถึงป้าย",
                                bus_name, route_name, stop_name,
                                curr_lat, curr_lon, dist, timestamp
                            )
                            queue_email(subject, body)
                            logger.info(
                                "[ถึงป้าย] %s ที่ %s (%s) ระยะ=%.1f ม.",
                                bus_name, stop_name, route_name, dist
                            )

        # --- ตรวจสอบการออกจากป้าย (Hysteresis) ---
        for stop_name, status in list(bus_stop_status[bus_id].items()):
            if status == "arrived" and stop_name not in currently_near:
                stop_coord = _find_stop_coord(stop_name)
                if stop_coord:
                    dist = calculate_distance(
                        curr_lat, curr_lon,
                        stop_coord["lat"], stop_coord["lon"]
                    )
                    if dist > CONFIG.departure_radius:
                        bus_stop_status[bus_id][stop_name] = "departed"

                        timestamp = datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        subject = (
                            f"[รถออกจากป้าย] {bus_name} "
                            f"ออกจาก {stop_name}"
                        )
                        body = _build_email_body(
                            "แจ้งเตือนรถเมล์ออกจากป้าย",
                            bus_name, None, stop_name,
                            curr_lat, curr_lon, dist, timestamp
                        )
                        queue_email(subject, body)
                        logger.info(
                            "[ออกจากป้าย] %s จาก %s ระยะ=%.1f ม.",
                            bus_name, stop_name, dist
                        )


def _build_email_body(
    title: str, bus_name: str, route_name: Optional[str],
    stop_name: str, lat: float, lon: float,
    dist: float, timestamp: str
) -> str:
    """สร้างเนื้อหาอีเมล HTML"""
    route_row = ""
    if route_name:
        route_row = f"""
              <tr>
                <td><strong>สาย</strong></td>
                <td>{route_name}</td>
              </tr>"""

    return f"""
    <h2>{title}</h2>
    <table border="1" cellpadding="8" cellspacing="0"
           style="border-collapse:collapse; font-family:sans-serif;">
      <tr>
        <td><strong>รถเมล์</strong></td>
        <td>{bus_name}</td>
      </tr>{route_row}
      <tr>
        <td><strong>ป้าย</strong></td>
        <td>{stop_name}</td>
      </tr>
      <tr>
        <td><strong>พิกัด</strong></td>
        <td>{lat:.8f}, {lon:.8f}</td>
      </tr>
      <tr>
        <td><strong>ระยะห่าง</strong></td>
        <td>{dist:.2f} เมตร</td>
      </tr>
      <tr>
        <td><strong>เวลา</strong></td>
        <td>{timestamp}</td>
      </tr>
    </table>
    """


def _find_stop_coord(stop_name: str) -> Optional[dict]:
    """ค้นหาพิกัดของป้ายจากชื่อ"""
    for route in BUS_STOPS:
        for stop in route["stops"]:
            if stop["name"] == stop_name:
                return stop
    return None


# ==============================================================================
# จัดการ Token
# ==============================================================================
def fetch_new_token() -> bool:
    """ขอ JWT Token ใหม่จากเซิร์ฟเวอร์"""
    try:
        url = f"{CONFIG.base_url}/api/auth/login/public"
        r = requests.post(
            url, json={"publicId": CONFIG.public_id}, timeout=15
        )
        r.raise_for_status()
        data = r.json()
        token = data["token"]
        token_info["token"] = token
        token_info["exp"] = decode_jwt_exp(token)

        if token_info["exp"]:
            exp_text = datetime.fromtimestamp(
                token_info["exp"]
            ).strftime("%Y-%m-%d %H:%M:%S")
        else:
            exp_text = "ไม่ทราบ"

        logger.info("รีเฟรช Token สำเร็จ, หมดอายุ=%s", exp_text)
        return True
    except Exception as e:
        logger.error("ขอ Token ล้มเหลว: %s", e)
        return False


def token_expired() -> bool:
    """ตรวจสอบว่า Token หมดอายุหรือใกล้หมดอายุ"""
    return (token_info["exp"] - time.time()) < CONFIG.token_refresh_margin


def ensure_token():
    """ตรวจสอบให้แน่ใจว่ามี Token ที่ใช้ได้"""
    if not token_info["token"] or token_expired():
        fetch_new_token()


# ==============================================================================
# แสดงผล
# ==============================================================================
def get_all_bus_rows() -> list:
    """ดึงข้อมูลรถเมล์ทั้งหมดเป็น list ที่เรียงลำดับแล้ว"""
    rows = []
    with state_lock:
        for eid, entity in bus_state.items():
            ts = entity.get("TIME_SERIES", {})
            lat = ts.get("latitude", {}).get("value")
            lon = ts.get("longitude", {}).get("value")
            rows.append({
                "id": eid,
                "name": entity.get(
                    "ENTITY_FIELD", {}
                ).get("name", {}).get("value", "-"),
                "lat": lat or "-",
                "lon": lon or "-",
                "place": get_place_name(lat, lon),
                "speed": ts.get("speed", {}).get("value") or 0,
                "status": ts.get("status", {}).get("value", "-"),
                "seats": ts.get(
                    "availableSeats", {}
                ).get("value") or "-",
            })
    rows.sort(key=lambda x: str(x["name"]))
    return rows


def print_bus_table():
    """แสดงตารางรถเมล์ที่กำลังติดตาม (กรองตามที่เลือก)"""
    if menu_active.is_set():
        return

    all_rows = get_all_bus_rows()

    with selection_lock:
        show_all = monitor_all
        selected_ids = set(monitored_bus_ids)
        email_ids = set(email_bus_ids)

    if show_all:
        rows = all_rows
    else:
        rows = [r for r in all_rows if r["id"] in selected_ids]

    os.system("cls" if os.name == "nt" else "clear")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"  [{now}] ระบบติดตามรถเมล์ มทส.")
    if show_all:
        print("  โหมด: แสดงรถเมล์ทั้งหมด")
    else:
        print(f"  โหมด: แสดงรถเมล์ที่เลือก {len(selected_ids)} คัน")

    email_count = len(email_ids)
    if email_count > 0:
        print(f"  แจ้งเตือนอีเมล: เปิดสำหรับ {email_count} คัน")
    else:
        print("  แจ้งเตือนอีเมล: ปิด")

    print()
    print("=" * 135)
    print(
        f"  {'#':3} {'ชื่อรถ':22} {'ละติจูด':14} {'ลองจิจูด':14} "
        f"{'ตำแหน่ง':30} {'ความเร็ว':8} {'สถานะ':14} "
        f"{'ที่นั่ง':6} {'อีเมล':6}"
    )
    print("-" * 135)

    for i, r in enumerate(rows, 1):
        lat_str = (
            f"{float(r['lat']):.8f}" if r["lat"] != "-" else "-"
        )
        lon_str = (
            f"{float(r['lon']):.8f}" if r["lon"] != "-" else "-"
        )
        try:
            speed_str = f"{float(r['speed']):>6.1f}"
        except (ValueError, TypeError):
            speed_str = "   0.0"

        email_flag = "*" if r["id"] in email_ids else ""

        print(
            f"  {i:3} {str(r['name'])[:22]:22} "
            f"{lat_str:14} {lon_str:14} "
            f"{str(r['place'])[:30]:30} {speed_str:>8} "
            f"{str(r['status'])[:14]:14} "
            f"{str(r['seats'])[:6]:6} {email_flag:6}"
        )

    print("=" * 135)
    print(
        f"  กำลังติดตาม {len(rows)}/{len(all_rows)} คัน | "
        f"รัศมีถึงป้าย: {CONFIG.arrival_radius} ม. | "
        f"รัศมีออกป้าย: {CONFIG.departure_radius} ม."
    )
    print()
    print("  กด 'm' + Enter = เปิดเมนู  |  กด 'q' + Enter = ออก")


# ==============================================================================
# เมนูโต้ตอบ
# ==============================================================================
def show_menu():
    """แสดงเมนูสำหรับเลือกรถเมล์และตั้งค่าอีเมล"""
    global monitor_all

    menu_active.set()
    time.sleep(0.3)

    while True:
        os.system("cls" if os.name == "nt" else "clear")
        print("=" * 60)
        print("  ระบบติดตามรถเมล์ มทส. - เมนูตั้งค่า")
        print("=" * 60)
        print()
        print("  1. แสดงรถเมล์ทั้งหมด (รีเซ็ตตัวกรอง)")
        print("  2. เลือกรถเมล์ที่ต้องการติดตาม")
        print("  3. ตั้งค่าแจ้งเตือนอีเมลสำหรับรถเมล์")
        print("  4. ตั้งค่าอีเมล (SMTP)")
        print("  5. ดูการตั้งค่าปัจจุบัน")
        print("  0. กลับไปหน้าติดตาม")
        print()

        choice = input("  เลือกเมนู: ").strip()

        if choice == "1":
            with selection_lock:
                monitor_all = True
                monitored_bus_ids.clear()
            print("\n  [สำเร็จ] แสดงรถเมล์ทั้งหมดแล้ว")
            input("  กด Enter เพื่อดำเนินการต่อ...")

        elif choice == "2":
            _menu_select_buses()

        elif choice == "3":
            _menu_configure_email_alerts()

        elif choice == "4":
            _menu_configure_smtp()

        elif choice == "5":
            _menu_view_settings()

        elif choice == "0":
            break

    menu_active.clear()
    print_bus_table()


def _menu_select_buses():
    """เมนูย่อย: เลือกรถเมล์ที่จะแสดง"""
    global monitor_all

    all_rows = get_all_bus_rows()

    if not all_rows:
        print("\n  [!] ยังไม่มีข้อมูลรถเมล์ กรุณารอสักครู่แล้วลองอีกครั้ง")
        input("  กด Enter เพื่อดำเนินการต่อ...")
        return

    os.system("cls" if os.name == "nt" else "clear")
    print("=" * 60)
    print("  เลือกรถเมล์ที่ต้องการติดตาม")
    print("=" * 60)
    print()
    print("  รถเมล์ที่พร้อมใช้งาน:")
    print()

    for i, r in enumerate(all_rows, 1):
        with selection_lock:
            is_selected = (
                monitor_all or r["id"] in monitored_bus_ids
            )
        marker = "[x]" if is_selected else "[ ]"
        status_str = str(r["status"])[:15]
        print(f"  {i:3}. {marker} {r['name']:25} ({status_str})")

    print()
    print("  ใส่หมายเลขรถคั่นด้วยคอมมา (เช่น 1,3,5)")
    print("  พิมพ์ 'all' เพื่อติดตามทั้งหมด")
    print("  พิมพ์ '0' เพื่อยกเลิก")
    print()

    choice = input("  เลือก: ").strip()

    if choice == "0":
        return

    if choice.lower() == "all":
        with selection_lock:
            monitor_all = True
            monitored_bus_ids.clear()
        print("\n  [สำเร็จ] แสดงรถเมล์ทั้งหมดแล้ว")
        input("  กด Enter เพื่อดำเนินการต่อ...")
        return

    try:
        indices = [int(x.strip()) for x in choice.split(",")]
        new_ids = set()
        names = []
        for idx in indices:
            if 1 <= idx <= len(all_rows):
                bus = all_rows[idx - 1]
                new_ids.add(bus["id"])
                names.append(bus["name"])

        if new_ids:
            with selection_lock:
                monitor_all = False
                monitored_bus_ids.clear()
                monitored_bus_ids.update(new_ids)

            print(f"\n  [สำเร็จ] กำลังติดตาม {len(new_ids)} คัน:")
            for name in names:
                print(f"       - {name}")
        else:
            print("\n  [!] ไม่มีรายการที่ถูกต้อง")

    except ValueError:
        print("\n  [!] ข้อมูลไม่ถูกต้อง")

    input("  กด Enter เพื่อดำเนินการต่อ...")


def _menu_configure_email_alerts():
    """เมนูย่อย: เลือกรถเมล์ที่ต้องการแจ้งเตือนอีเมล"""
    all_rows = get_all_bus_rows()

    if not all_rows:
        print("\n  [!] ยังไม่มีข้อมูลรถเมล์ กรุณารอสักครู่แล้วลองอีกครั้ง")
        input("  กด Enter เพื่อดำเนินการต่อ...")
        return

    while True:
        os.system("cls" if os.name == "nt" else "clear")
        print("=" * 60)
        print("  ตั้งค่าแจ้งเตือนอีเมล")
        print("=" * 60)

        if not CONFIG.sender_email:
            print()
            print("  [คำเตือน] ยังไม่ได้ตั้งค่าอีเมล!")
            print("  ไปที่เมนูหลัก ตัวเลือก 4 เพื่อตั้งค่า SMTP ก่อน")
            print()

        print()
        print("  เลือกรถเมล์ที่ต้องการรับแจ้งเตือน:")
        print()

        for i, r in enumerate(all_rows, 1):
            with selection_lock:
                has_email = r["id"] in email_bus_ids
            marker = "[แจ้งเตือน]" if has_email else "[         ]"
            print(f"  {i:3}. {marker} {r['name']:25}")

        print()
        print("  คำสั่ง:")
        print("    ใส่หมายเลขเพื่อ สลับ เปิด/ปิด อีเมล (เช่น 1,3,5)")
        print("    'all'  - เปิดอีเมลทุกคัน")
        print("    'none' - ปิดอีเมลทั้งหมด")
        print("    '0'    - กลับเมนูหลัก")
        print()

        choice = input("  เลือก: ").strip()

        if choice == "0":
            return

        if choice.lower() == "all":
            with selection_lock:
                email_bus_ids.clear()
                for r in all_rows:
                    email_bus_ids.add(r["id"])
            print(
                f"\n  [สำเร็จ] เปิดแจ้งเตือนอีเมลทั้งหมด "
                f"{len(all_rows)} คัน"
            )
            input("  กด Enter เพื่อดำเนินการต่อ...")
            continue

        if choice.lower() == "none":
            with selection_lock:
                email_bus_ids.clear()
            print("\n  [สำเร็จ] ปิดแจ้งเตือนอีเมลทั้งหมดแล้ว")
            input("  กด Enter เพื่อดำเนินการต่อ...")
            continue

        try:
            indices = [int(x.strip()) for x in choice.split(",")]
            for idx in indices:
                if 1 <= idx <= len(all_rows):
                    bus = all_rows[idx - 1]
                    with selection_lock:
                        if bus["id"] in email_bus_ids:
                            email_bus_ids.discard(bus["id"])
                            print(
                                f"  [-] ปิดอีเมล: {bus['name']}"
                            )
                        else:
                            email_bus_ids.add(bus["id"])
                            print(
                                f"  [+] เปิดอีเมล: {bus['name']}"
                            )
        except ValueError:
            print("\n  [!] ข้อมูลไม่ถูกต้อง")

        input("  กด Enter เพื่อดำเนินการต่อ...")


def _menu_configure_smtp():
    """เมนูย่อย: ตั้งค่าอีเมล SMTP"""
    os.system("cls" if os.name == "nt" else "clear")
    print("=" * 60)
    print("  ตั้งค่าอีเมล SMTP")
    print("=" * 60)
    print()
    print(f"  เซิร์ฟเวอร์ SMTP  : {CONFIG.smtp_server}")
    print(f"  พอร์ต SMTP       : {CONFIG.smtp_port}")
    print(f"  อีเมลผู้ส่ง       : {CONFIG.sender_email or '(ยังไม่ตั้งค่า)'}")
    print(f"  รหัสผ่านผู้ส่ง     : {'****' if CONFIG.sender_password else '(ยังไม่ตั้งค่า)'}")
    print(f"  อีเมลผู้รับ       : {CONFIG.recipient_email or '(ยังไม่ตั้งค่า)'}")
    print()
    print("  กรอกค่าใหม่ (กด Enter เพื่อใช้ค่าเดิม):")
    print()

    val = input(f"  เซิร์ฟเวอร์ SMTP [{CONFIG.smtp_server}]: ").strip()
    if val:
        CONFIG.smtp_server = val

    val = input(f"  พอร์ต SMTP [{CONFIG.smtp_port}]: ").strip()
    if val:
        try:
            CONFIG.smtp_port = int(val)
        except ValueError:
            print("  [!] พอร์ตไม่ถูกต้อง ใช้ค่าเดิม")

    val = input(f"  อีเมลผู้ส่ง [{CONFIG.sender_email}]: ").strip()
    if val:
        CONFIG.sender_email = val

    val = input("  รหัสผ่าน (App Password): ").strip()
    if val:
        CONFIG.sender_password = val

    val = input(
        f"  อีเมลผู้รับ [{CONFIG.recipient_email}]: "
    ).strip()
    if val:
        CONFIG.recipient_email = val

    print()
    print("  [สำเร็จ] บันทึกการตั้งค่าอีเมลแล้ว")

    # ตัวเลือกทดสอบ
    test = input("  ส่งอีเมลทดสอบหรือไม่? (y/n): ").strip().lower()
    if test == "y":
        subject = "[ระบบติดตามรถเมล์ มทส.] อีเมลทดสอบ"
        body = f"""
        <h2>อีเมลทดสอบ</h2>
        <p>นี่คืออีเมลทดสอบจากระบบติดตามรถเมล์ มทส.</p>
        <p>เวลา: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p>หากคุณได้รับอีเมลนี้ แสดงว่าระบบแจ้งเตือนทำงานปกติ</p>
        """
        send_email_impl(subject, body)
        print("  ส่งอีเมลทดสอบแล้ว (ตรวจสอบกล่องจดหมายและ log)")

    input("\n  กด Enter เพื่อดำเนินการต่อ...")


def _menu_view_settings():
    """เมนูย่อย: ดูการตั้งค่าปัจจุบันทั้งหมด"""
    os.system("cls" if os.name == "nt" else "clear")
    print("=" * 60)
    print("  การตั้งค่าปัจจุบัน")
    print("=" * 60)
    print()

    with selection_lock:
        show_all = monitor_all
        sel_ids = set(monitored_bus_ids)
        em_ids = set(email_bus_ids)

    print("  [การติดตาม]")
    if show_all:
        print("    โหมด           : รถเมล์ทั้งหมด")
    else:
        print(f"    โหมด           : เลือก {len(sel_ids)} คัน")

    all_rows = get_all_bus_rows()

    if not show_all and sel_ids:
        print("    รถที่ติดตาม:")
        for r in all_rows:
            if r["id"] in sel_ids:
                print(f"      - {r['name']}")

    print()
    print("  [แจ้งเตือนอีเมล]")
    if em_ids:
        print(f"    เปิดสำหรับ {len(em_ids)} คัน:")
        for r in all_rows:
            if r["id"] in em_ids:
                print(f"      - {r['name']}")
    else:
        print("    ไม่มีรถที่เปิดแจ้งเตือนอีเมล")

    print()
    print("  [ตั้งค่าอีเมล]")
    print(f"    เซิร์ฟเวอร์ SMTP : {CONFIG.smtp_server}")
    print(f"    พอร์ต SMTP      : {CONFIG.smtp_port}")
    print(f"    ผู้ส่ง           : {CONFIG.sender_email or '(ยังไม่ตั้งค่า)'}")
    print(f"    ผู้รับ           : {CONFIG.recipient_email or '(ยังไม่ตั้งค่า)'}")

    print()
    print("  [ค่าระยะทาง]")
    print(f"    รัศมีถึงป้าย     : {CONFIG.arrival_radius} เมตร")
    print(f"    รัศมีออกจากป้าย  : {CONFIG.departure_radius} เมตร")
    print(f"    ช่วงพักแจ้งเตือน : {CONFIG.notification_cooldown} วินาที")

    print()
    input("  กด Enter เพื่อดำเนินการต่อ...")


# ==============================================================================
# WebSocket Payload
# ==============================================================================
def build_subscribe_payload() -> dict:
    """สร้างคำสั่ง subscribe สำหรับ ThingsBoard"""
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


# ==============================================================================
# WebSocket Callbacks
# ==============================================================================
def on_open(ws):
    """เรียกเมื่อเชื่อมต่อ WebSocket สำเร็จ"""
    logger.info("เชื่อมต่อ WebSocket สำเร็จ")

    ensure_token()

    auth_payload = {
        "authCmd": {
            "cmdId": 0,
            "token": token_info["token"]
        }
    }
    ws.send(json.dumps(auth_payload))
    logger.info("ส่งคำสั่งยืนยันตัวตนแล้ว")

    subscribe_payload = build_subscribe_payload()
    ws.send(json.dumps(subscribe_payload))
    logger.info("ส่งคำสั่ง subscribe แล้ว")


def on_message(ws, message):
    """เรียกเมื่อได้รับข้อความจาก WebSocket"""
    try:
        msg = json.loads(message)

        # ตรวจสอบข้อผิดพลาดจากเซิร์ฟเวอร์
        error_code = msg.get("errorCode")
        error_msg = msg.get("errorMsg")

        if error_msg is not None:
            logger.error(
                "เซิร์ฟเวอร์ผิดพลาด: code=%s msg=%s",
                error_code, error_msg
            )
            ws.close()
            return

        if error_code is not None and error_code != 0:
            logger.error("รหัสผิดพลาดจากเซิร์ฟเวอร์: %s", error_code)
            ws.close()
            return

        # ดึงข้อมูลจาก initial load หรือ update push
        data_wrapper = msg.get("data")
        data = None
        update = msg.get("update")

        if data_wrapper and isinstance(data_wrapper, dict):
            data = data_wrapper.get("data")
        elif isinstance(data_wrapper, list):
            data = data_wrapper

        if update and isinstance(update, list):
            data = update

        if not data or not isinstance(data, list):
            return

        # อัปเดตสถานะ
        with state_lock:
            for item in data:
                if not isinstance(item, dict):
                    continue

                entity_id = item.get("entityId")
                if not entity_id or not isinstance(entity_id, dict):
                    continue

                eid = entity_id.get("id")
                if not eid:
                    continue

                if eid not in bus_state:
                    bus_state[eid] = {
                        "ENTITY_FIELD": {},
                        "TIME_SERIES": {}
                    }

                latest = item.get("latest", {})
                if not isinstance(latest, dict):
                    continue

                for section in ["ENTITY_FIELD", "TIME_SERIES"]:
                    if (section in latest
                            and isinstance(latest[section], dict)):
                        bus_state[eid][section].update(latest[section])

        # ตรวจสอบป้ายสำหรับรถที่เปิดแจ้งเตือนอีเมล
        for item in data:
            if not isinstance(item, dict):
                continue

            entity_id = item.get("entityId")
            if not entity_id or not isinstance(entity_id, dict):
                continue

            eid = entity_id.get("id")
            if not eid:
                continue

            with state_lock:
                entity = bus_state.get(eid, {})
                lat = get_entity_value(
                    entity, "TIME_SERIES", "latitude"
                )
                lon = get_entity_value(
                    entity, "TIME_SERIES", "longitude"
                )
                name = get_entity_value(
                    entity, "ENTITY_FIELD", "name"
                ) or eid

            check_bus_at_stop(eid, name, lat, lon)

        print_bus_table()

    except json.JSONDecodeError as e:
        logger.error("ถอดรหัส JSON ผิดพลาด: %s", e)
    except Exception as e:
        logger.error("ประมวลผลข้อความผิดพลาด: %s", e, exc_info=True)


def on_error(ws, error):
    """เรียกเมื่อเกิดข้อผิดพลาด WebSocket"""
    logger.error("WebSocket ผิดพลาด: %s", error)


def on_close(ws, close_status_code, close_msg):
    """เรียกเมื่อ WebSocket ถูกปิด"""
    logger.warning(
        "WebSocket ถูกปิด: code=%s msg=%s",
        close_status_code, close_msg
    )


# ==============================================================================
# ตรวจสอบ Token อัตโนมัติ
# ==============================================================================
def token_refresh_watcher():
    """เธรดพื้นหลังที่คอยตรวจสอบ Token หมดอายุและเชื่อมต่อใหม่"""
    global ws_app
    while True:
        try:
            time.sleep(30)
            if token_info["token"] and token_expired():
                logger.info("Token ใกล้หมดอายุ กำลังรีเฟรช...")
                fetch_new_token()
                with ws_lock:
                    if ws_app:
                        try:
                            ws_app.close()
                        except Exception:
                            pass
        except Exception as e:
            logger.error("ตรวจสอบ Token ผิดพลาด: %s", e)


# ==============================================================================
# รับคำสั่งจากผู้ใช้ (ทำงานในเธรดพื้นหลัง)
# ==============================================================================
def input_listener():
    """เธรดพื้นหลังที่รอรับคำสั่งจากแป้นพิมพ์"""
    while True:
        try:
            cmd = input().strip().lower()
            if cmd == "m":
                show_menu()
            elif cmd == "q":
                logger.info("ผู้ใช้สั่งออกจากโปรแกรม")
                os._exit(0)
        except EOFError:
            break
        except Exception:
            pass


# ==============================================================================
# ลูปหลัก
# ==============================================================================
def run_forever():
    """ลูปเชื่อมต่อ WebSocket หลักพร้อมระบบเชื่อมต่อใหม่อัตโนมัติ"""
    global ws_app
    while True:
        try:
            ensure_token()
            logger.info(
                "กำลังเชื่อมต่อ WebSocket ที่ %s ...", CONFIG.ws_url
            )

            with ws_lock:
                ws_app = websocket.WebSocketApp(
                    CONFIG.ws_url,
                    header={"Origin": CONFIG.base_url},
                    on_open=on_open,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close
                )

            ws_app.run_forever(
                ping_interval=CONFIG.ping_interval,
                ping_timeout=CONFIG.ping_timeout
            )

        except KeyboardInterrupt:
            logger.info("ผู้ใช้หยุดโปรแกรม")
            break
        except Exception as e:
            logger.error("เชื่อมต่อล้มเหลว: %s", e)

        logger.info(
            "เชื่อมต่อใหม่ใน %d วินาที...", CONFIG.reconnect_delay
        )
        time.sleep(CONFIG.reconnect_delay)


# ==============================================================================
# จุดเริ่มต้นโปรแกรม
# ==============================================================================
if __name__ == "__main__":
    # เริ่มเธรดส่งอีเมล
    email_thread = threading.Thread(target=email_worker, daemon=True)
    email_thread.start()

    # เริ่มเธรดตรวจสอบ Token
    watcher_thread = threading.Thread(
        target=token_refresh_watcher, daemon=True
    )
    watcher_thread.start()

    # เริ่มเธรดรับคำสั่งผู้ใช้
    input_thread = threading.Thread(target=input_listener, daemon=True)
    input_thread.start()

    logger.info("เริ่มต้นระบบติดตามรถเมล์ มทส.")
    logger.info(
        "ตั้งค่า: รัศมีถึงป้าย=%s ม., รัศมีออกป้าย=%s ม., "
        "ช่วงพัก=%s วินาที",
        CONFIG.arrival_radius,
        CONFIG.departure_radius,
        CONFIG.notification_cooldown
    )

    print()
    print("  กำลังรอข้อมูลรถเมล์...")
    print("  กด 'm' + Enter เพื่อเปิดเมนูเมื่อมีข้อมูลแล้ว")
    print()

    run_forever()