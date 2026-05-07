import socket
import json
import time

SERVER_IP = "127.0.0.1"
SERVER_PORT = 9000

def run_client():
    try:
        # 1. สร้าง Socket และเชื่อมต่อ
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((SERVER_IP, SERVER_PORT))
            print(f"Connected to Bus Server at {SERVER_IP}:{SERVER_PORT}")
            
            while True:
                # 2. ส่งคำสั่งให้ Server
                s.sendall(b"LIST\n")
                
                # 3. รับข้อมูล (Buffer ขนาดใหญ่สำหรับ JSON)
                data = s.recv(4096).decode()
                if not data: break
                
                # 4. แปลงข้อมูลและแสดงผล
                bus_data = json.loads(data)
                print(f"\n--- Bus Update at {time.strftime('%H:%M:%S')} ---")
                for eid, values in bus_data.items():
                    # ดึงค่าละติจูดจากโครงสร้าง ThingsBoard
                    lat = values.get("TIME_SERIES", {}).get("latitude", {}).get("value", "-")
                    print(f"Bus ID: {eid[:8]}... | Latitude: {lat}")
                
                # หน่วงเวลา 5 วินาทีก่อนขอข้อมูลใหม่
                time.sleep(5)

    except ConnectionRefusedError:
        print("Cannot connect to server. Is it running?")
    except KeyboardInterrupt:
        print("\nClient stopped.")

if __name__ == "__main__":
    run_client()