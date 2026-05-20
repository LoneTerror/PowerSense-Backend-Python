import subprocess
import sys
import os
import time
import argparse

def print_dashboard():
    # Clear terminal cleanly depending on the OS environment
    os.system('cls' if os.name == 'nt' else 'clear')
    print("="*65)
    print(" 🚀 POWERSENSE PRODUCTION CONTAINER CLUSTER ACTIVE")
    print("="*65)

    print("\n 🔐 AUTH SERVICE (Port 8000)")
    print(" ----------------------------------------------------")
    print("   Status : Active & Inbound Bound to 0.0.0.0")
    
    print("\n 🔌 DEVICE SERVICE (Port 8001)")
    print(" ----------------------------------------------------")
    print("   Status : Active & Inbound Bound to 0.0.0.0")

    print("\n 📡 TELEMETRY SERVICE (Port 8002)")
    print(" ----------------------------------------------------")
    print("   Status : Active & Inbound Bound to 0.0.0.0")

    print("\n 👤 USER SERVICE (Port 8003)")
    print(" ----------------------------------------------------")
    print("   Status : Active & Inbound Bound to 0.0.0.0")
    print("\n" + "="*65 + "\n")

def main():
    # Keep your parser configuration intact
    parser = argparse.ArgumentParser(description="Start the PowerSense Cluster.")
    parser.add_argument('--docs', action='store_true', help="Ignored in headless production mode")
    args = parser.parse_args()

    print_dashboard()

    # Dynamic Binary Resolver: Accounts for localized Pterodactyl pip binary bins
    if os.name == "nt":
        venv_uvicorn = os.path.join("venv", "Scripts", "uvicorn")
        uvicorn = venv_uvicorn if os.path.exists(venv_uvicorn) else "uvicorn"
    else:
        venv_uvicorn = os.path.join("venv", "bin", "uvicorn")
        local_user_uvicorn = "/home/container/.local/bin/uvicorn"
        
        if os.path.exists(venv_uvicorn):
            uvicorn = venv_uvicorn
        elif os.path.exists(local_user_uvicorn):
            uvicorn = local_user_uvicorn  # <-- Safely catches Pterodactyl local installations
        else:
            uvicorn = "uvicorn"  # Global fallback

    # Worker Node Execution Config
    auth_cmd = [uvicorn, "src.auth.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
    device_cmd = [uvicorn, "src.device.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
    telemetry_cmd = [uvicorn, "src.telemetry.main:app", "--host", "0.0.0.0", "--port", "8002", "--reload"]
    user_cmd = [uvicorn, "src.user.main:app", "--host", "0.0.0.0", "--port", "8003", "--reload"]

    try:
        p0 = subprocess.Popen(auth_cmd)
        time.sleep(0.5)
        p1 = subprocess.Popen(device_cmd)
        time.sleep(0.5) 
        p2 = subprocess.Popen(telemetry_cmd)
        time.sleep(0.5)
        p3 = subprocess.Popen(user_cmd)
        
        p0.wait()
        p1.wait()
        p2.wait()
        p3.wait()
        
    except KeyboardInterrupt:
        print("\n🛑 Gracefully shutting down microservices...")
        p0.terminate()
        p1.terminate()
        p2.terminate()
        p3.terminate()
        sys.exit(0)

if __name__ == "__main__":
    main()