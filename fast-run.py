# fast-run.py
import subprocess
import sys
import os

def main():
    print("🚀 Starting PowerSense Development Cluster...")
    print("⚡ Hot-reloading is ENABLED. Press Ctrl+C to stop.\n")
    
    uvicorn = os.path.join("venv", "Scripts", "uvicorn") if os.name == "nt" else os.path.join("venv", "bin", "uvicorn")

    # Command arguments for both services
    telemetry_cmd = [uvicorn, "services.telemetry_service.app.main:app", "--host", "0.0.0.0", "--port", "8002", "--reload"]
    device_cmd = [uvicorn, "services.device_service.app.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]

    try:
        # Popen runs them concurrently without blocking each other
        p1 = subprocess.Popen(telemetry_cmd)
        p2 = subprocess.Popen(device_cmd)
        
        # Wait for them to finish (which is never, unless they crash or you hit Ctrl+C)
        p1.wait()
        p2.wait()
        
    except KeyboardInterrupt:
        print("\n🛑 Gracefully shutting down microservices...")
        p1.terminate()
        p2.terminate()
        sys.exit(0)

if __name__ == "__main__":
    main()