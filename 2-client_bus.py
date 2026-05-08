import socket
import json
import time
import os

SERVER_IP, SERVER_PORT = "127.0.0.1", 9000
BUFFER_SIZE = 65536
BUS_LIST = [f"SUT NEW BUS {i}" for i in [1, 10, 11, 12, 2, 3, 4, 5, 6, 7, 8, 9]]

def get_v(d, section, key):
    return d.get(section, {}).get(key, {}).get("value", "-")

def run_client():
    print("\nSelect Bus: 1-12 or 0 (Track All)")
    choice = input("Choice: ")
    target_bus = BUS_LIST[int(choice) - 1] if choice.isdigit() and int(choice) > 0 else "ALL"

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((SERVER_IP, SERVER_PORT))
            while True:
                s.sendall(b"LIST\n")
                raw = b""
                while True:
                    part = s.recv(BUFFER_SIZE)
                    raw += part
                    if len(part) < BUFFER_SIZE: break
                
                try: bus_data = json.loads(raw.decode())
                except: continue

                os.system("cls" if os.name == "nt" else "clear")
                print(f"--- 🚌 Tracking: {target_bus} | {time.strftime('%H:%M:%S')} ---")
                print(f"{'NAME':20} {'LAT':12} {'LON':12} {'SPEED':8} {'STATUS'}")
                print("-" * 75)

                for eid, values in bus_data.items():
                    name = get_v(values, "ENTITY_FIELD", "name")
                    if target_bus == "ALL" or target_bus == name:
                        lat = get_v(values, "TIME_SERIES", "latitude")
                        lon = get_v(values, "TIME_SERIES", "longitude")
                        speed = get_v(values, "TIME_SERIES", "speed")
                        status = get_v(values, "TIME_SERIES", "status")
                        print(f"{name:20} {str(lat)[:10]:12} {str(lon)[:10]:12} {str(speed):8} {status}")
                
                print("-" * 75)
                time.sleep(2)
    except Exception as e: print(f"Error: {e}")

if __name__ == "__main__":
    run_client()