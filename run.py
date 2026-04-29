# run.py
import subprocess
import sys
import os

def main():
    print("🏭 Starting PowerSense Production Cluster...")
    print("⚙️ Multi-worker processing is ENABLED. Hot-reloading is DISABLED.\n")
    
    uvicorn = os.path.join("venv", "Scripts", "uvicorn") if os.name == "nt" else os.path.join("venv", "bin", "uvicorn")

    # The Telemetry service gets 4 workers due to high-frequency WebSocket loads
    telemetry_cmd = [uvicorn, "services.telemetry_service.app.main:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "4"]
    
    # The Device service gets 2 workers as relay switching is relatively low-frequency
    device_cmd = [uvicorn, "services.device_service.app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2"]

    try:
        p1 = subprocess.Popen(telemetry_cmd)
        p2 = subprocess.Popen(device_cmd)
        
        p1.wait()
        p2.wait()
        
    except KeyboardInterrupt:
        print("\n🛑 Shutting down production cluster...")
        p1.terminate()
        p2.terminate()
        sys.exit(0)

if __name__ == "__main__":
    main()