import socket
import json
import time
import threading
import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


# --- CONFIGURATION ---
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 9000

SMTP_CONFIG = {
    "server": "smtp.gmail.com",
    "port": 587,
    "email": "sutnewbus.send@gmail.com",
    "password": "ucki eult ftjq mddn",
}


# --- ตัวแปรระบบ ---
local_bus_data = {}
data_lock = threading.Lock()
running = True


# =====================================================================
# ส่วนที่ 1: ดึงข้อมูลจาก Server (Persistent Connection)
# =====================================================================

def fetch_data_loop():
    """เชื่อมต่อครั้งเดียว แล้วส่ง GET_BUS ซ้ำผ่าน socket เดิม"""
    global local_bus_data
    while running:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((SERVER_HOST, SERVER_PORT))

            while running:
                sock.sendall(b"GET_BUS")

                buf = b""
                while b"\n" not in buf:
                    chunk = sock.recv(65536)
                    if not chunk:
                        raise ConnectionError("Server ปิดการเชื่อมต่อ")
                    buf += chunk

                line = buf.split(b"\n")[0]
                result = json.loads(line.decode("utf-8"))
                with data_lock:
                    local_bus_data = result
                time.sleep(1)

        except Exception as e:
            print(f"[ผิดพลาด] {e} - เชื่อมต่อใหม่ใน 3 วินาที...")
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
        time.sleep(3)


# =====================================================================
# ส่วนที่ 2: สร้างตารางข้อมูลรถ
# =====================================================================

def build_table_text():
    """สร้างตารางรถเมล์เป็นข้อความ ใช้ได้ทั้งแสดงผลและส่งอีเมล"""
    with data_lock:
        snapshot = dict(local_bus_data)

    if not snapshot:
        return None, 0

    rows = sorted(snapshot.values(), key=lambda x: str(x.get("name", "")))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = []
    lines.append(f"[{now}] ระบบติดตามรถเมล์ มทส.")
    lines.append("=" * 120)
    lines.append(
        f"{'ชื่อรถ':18} "
        f"{'ตำแหน่ง':50} "
        f"{'ความเร็ว':10} "
        f"{'สถานะ':15} "
        f"{'ที่นั่ง':6}"
    )
    lines.append("-" * 120)

    for r in rows:
        name = str(r.get("name", "-"))[:18]
        location = str(r.get("location", "-"))[:50]
        speed = str(r.get("speed", "0"))[:10]
        status = str(r.get("status", "-"))[:15]
        seats = str(r.get("seats", "-"))[:6]
        lines.append(f"{name:18} {location:50} {speed:10} {status:15} {seats:6}")

    lines.append("=" * 120)
    lines.append(f"รถทั้งหมด: {len(rows)} คัน")

    return "\n".join(lines), len(rows)


def build_table_html():
    """สร้างตาราง HTML สำหรับส่งอีเมล (อ่านง่ายกว่าข้อความธรรมดา)"""
    with data_lock:
        snapshot = dict(local_bus_data)

    if not snapshot:
        return None

    rows = sorted(snapshot.values(), key=lambda x: str(x.get("name", "")))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, sans-serif; padding: 20px; }}
            h2 {{ color: #2c3e50; }}
            table {{ border-collapse: collapse; width: 100%; }}
            th {{ background-color: #3498db; color: white; padding: 10px; text-align: left; }}
            td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
            tr:nth-child(even) {{ background-color: #f2f2f2; }}
            tr:hover {{ background-color: #dbeafe; }}
            .status-on {{ color: #27ae60; font-weight: bold; }}
            .status-wait {{ color: #e67e22; font-weight: bold; }}
            .footer {{ margin-top: 20px; color: #7f8c8d; font-size: 12px; }}
        </style>
    </head>
    <body>
        <h2>ระบบติดตามรถเมล์ มทส.</h2>
        <p>ข้อมูล ณ เวลา: {now}</p>
        <table>
            <tr>
                <th>ชื่อรถ</th>
                <th>ตำแหน่ง</th>
                <th>ความเร็ว</th>
                <th>สถานะ</th>
                <th>ที่นั่งว่าง</th>
            </tr>
    """

    for r in rows:
        name = str(r.get("name", "-"))
        location = str(r.get("location", "-"))
        speed = str(r.get("speed", "0"))
        status = str(r.get("status", "-"))
        seats = str(r.get("seats", "-"))

        if "On route" in status:
            status_class = "status-on"
        else:
            status_class = "status-wait"

        html += f"""
            <tr>
                <td>{name}</td>
                <td>{location}</td>
                <td>{speed}</td>
                <td class="{status_class}">{status}</td>
                <td>{seats}</td>
            </tr>
        """

    html += f"""
        </table>
        <p class="footer">
            รถทั้งหมด: {len(rows)} คัน<br>
            ส่งจากระบบติดตามรถเมล์ มทส. อัตโนมัติ
        </p>
    </body>
    </html>
    """
    return html


# =====================================================================
# ส่วนที่ 3: ส่งอีเมล
# =====================================================================

def send_email(recipient_email):
    """ส่งตารางรถเมล์ไปยังอีเมลที่ระบุ"""
    try:
        # สร้างเนื้อหา
        table_text, count = build_table_text()
        table_html = build_table_html()

        if not table_text or not table_html:
            print("[ผิดพลาด] ยังไม่มีข้อมูลรถ ไม่สามารถส่งอีเมลได้")
            return False

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # สร้างอีเมล
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"สถานะรถเมล์ มทส. - {now} ({count} คัน)"
        msg["From"] = SMTP_CONFIG["email"]
        msg["To"] = recipient_email

        # แนบทั้ง text และ html (อีเมลจะเลือก html ถ้ารองรับ)
        msg.attach(MIMEText(table_text, "plain", "utf-8"))
        msg.attach(MIMEText(table_html, "html", "utf-8"))

        # ส่ง
        print(f"[อีเมล] กำลังส่งไปยัง {recipient_email}...")
        with smtplib.SMTP(SMTP_CONFIG["server"], SMTP_CONFIG["port"]) as server:
            server.starttls()
            server.login(SMTP_CONFIG["email"], SMTP_CONFIG["password"])
            server.send_message(msg)

        print(f"[อีเมล] ส่งสำเร็จไปยัง {recipient_email}")
        return True

    except smtplib.SMTPAuthenticationError:
        print("[ผิดพลาด] รหัสผ่านอีเมลไม่ถูกต้อง หรือยังไม่ได้เปิด App Password")
        return False
    except smtplib.SMTPRecipientsRefused:
        print(f"[ผิดพลาด] อีเมลปลายทางไม่ถูกต้อง: {recipient_email}")
        return False
    except Exception as e:
        print(f"[ผิดพลาด] ส่งอีเมลล้มเหลว: {e}")
        return False


# =====================================================================
# ส่วนที่ 4: แสดงผลรถทั้งหมด
# =====================================================================

def display_all_buses():
    """แสดงตารางรถทั้งหมด วนซ้ำอัตโนมัติ"""
    while running:
        table_text, count = build_table_text()
        if table_text:
            os.system("cls" if os.name == "nt" else "clear")
            print(table_text)
            print("[คำสั่ง] กด Ctrl+C เพื่อกลับเมนู")
        time.sleep(2)


# =====================================================================
# ส่วนที่ 5: ติดตามรถเฉพาะคัน
# =====================================================================

def track_single_bus(bus_id, bus_name):
    """ติดตามรถคันเดียว แสดงรายละเอียด"""
    print(f"\n[ติดตาม] กำลังติดตาม: {bus_name}")
    print("[ติดตาม] กด Ctrl+C เพื่อกลับเมนูหลัก\n")

    try:
        while running:
            with data_lock:
                bus = local_bus_data.get(bus_id)

            if bus:
                os.system("cls" if os.name == "nt" else "clear")
                now = datetime.now().strftime("%H:%M:%S")
                print(f"--- ติดตาม: {bus.get('name', '-')} | {now} ---")
                print("=" * 80)
                print(f"  ชื่อรถ       : {bus.get('name', '-')}")
                print(f"  ตำแหน่ง      : {bus.get('location', '-')}")
                print(f"  ละติจูด      : {bus.get('latitude', '-')}")
                print(f"  ลองจิจูด     : {bus.get('longitude', '-')}")
                print(f"  ความเร็ว     : {bus.get('speed', '0')}")
                print(f"  สถานะ        : {bus.get('status', '-')}")
                print(f"  ที่นั่งว่าง  : {bus.get('seats', '-')}")
                print(f"  อัปเดตล่าสุด : {bus.get('updated_at', '-')}")
                print("=" * 80)
                print("[กด Ctrl+C เพื่อกลับเมนูหลัก]")
            else:
                print(f"[รอ] ยังไม่ได้รับข้อมูลของ {bus_name}...")

            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[กลับ] กลับเมนูหลัก...")


# =====================================================================
# ส่วนที่ 6: เมนูเลือกรถ (เพิ่มตัวเลือกส่งอีเมล)
# =====================================================================

def show_bus_menu():
    """แสดงรายชื่อรถให้เลือก พร้อมตัวเลือกส่งอีเมล"""
    with data_lock:
        snapshot = dict(local_bus_data)

    if not snapshot:
        print("[รอ] ยังไม่มีข้อมูลรถ กรุณารอสักครู่...")
        return None, None

    buses = []
    for eid, data in sorted(snapshot.items(), key=lambda x: str(x[1].get("name", ""))):
        buses.append({"id": eid, "name": data.get("name", "-")})

    print("\n" + "=" * 50)
    print("  ระบบติดตามรถเมล์ มทส. (Client)")
    print("=" * 50)
    print("  0. แสดงรถทั้งหมด (ตาราง)")
    print("-" * 50)
    for i, b in enumerate(buses, 1):
        print(f"  {i}. ติดตาม {b['name']}")
    print("-" * 50)
    print(f"  E. ส่งตารางรถทั้งหมดทางอีเมล")
    print("=" * 50)

    try:
        choice = input("เลือกหมายเลข (หรือ E): ").strip()

        if choice.upper() == "E":
            return "__EMAIL__", None

        choice_num = int(choice)
        if choice_num == 0:
            return "__ALL__", None
        if 1 <= choice_num <= len(buses):
            return buses[choice_num - 1]["id"], buses[choice_num - 1]["name"]
    except (ValueError, IndexError):
        pass

    print("[ผิดพลาด] หมายเลขไม่ถูกต้อง")
    return None, None


def handle_email_menu():
    """เมนูส่งอีเมล"""
    print("\n" + "=" * 50)
    print("  ส่งตารางรถเมล์ทางอีเมล")
    print("=" * 50)

    # แสดงตัวอย่างตาราง
    table_text, count = build_table_text()
    if table_text:
        print("\n--- ตัวอย่างข้อมูลที่จะส่ง ---")
        print(table_text)
        print("--- จบตัวอย่าง ---\n")
    else:
        print("[ผิดพลาด] ยังไม่มีข้อมูลรถ")
        return

    email = input("พิมพ์อีเมลผู้รับ (หรือ 'n' เพื่อยกเลิก): ").strip()

    if email.lower() == "n" or not email:
        print("[ยกเลิก] กลับเมนูหลัก")
        return

    # ตรวจสอบรูปแบบอีเมลเบื้องต้น
    if "@" not in email or "." not in email:
        print("[ผิดพลาด] รูปแบบอีเมลไม่ถูกต้อง")
        return

    # ยืนยัน
    confirm = input(f"ยืนยันส่งไปยัง {email}? (y/n): ").strip().lower()
    if confirm != "y":
        print("[ยกเลิก] ไม่ส่งอีเมล")
        return

    # ส่ง (ใน thread แยก เพื่อไม่ให้ค้าง)
    print("[อีเมล] กำลังส่ง...")
    success = send_email(email)

    if success:
        input("\n[สำเร็จ] กด Enter เพื่อกลับเมนูหลัก...")
    else:
        input("\n[ล้มเหลว] กด Enter เพื่อกลับเมนูหลัก...")


# =====================================================================
# จุดเริ่มต้น
# =====================================================================

if __name__ == "__main__":
    print("=" * 50)
    print("  ระบบติดตามรถเมล์ มทส. (Client)")
    print(f"  เชื่อมต่อ: {SERVER_HOST}:{SERVER_PORT}")
    print("=" * 50)

    # เริ่ม Thread ดึงข้อมูล (Persistent Connection)
    threading.Thread(target=fetch_data_loop, daemon=True).start()

    print("\n[กำลังขอข้อมูลจาก Server...]")
    time.sleep(3)

    try:
        while running:
            bus_id, bus_name = show_bus_menu()

            if bus_id is None:
                time.sleep(1)
                continue

            if bus_id == "__ALL__":
                try:
                    display_all_buses()
                except KeyboardInterrupt:
                    print("\n[กลับ] กลับเมนูเลือกรถ...")
                    continue

            elif bus_id == "__EMAIL__":
                handle_email_menu()

            else:
                track_single_bus(bus_id, bus_name)

    except KeyboardInterrupt:
        print("\n\n[จบการทำงาน] ปิดโปรแกรม")
        running = False