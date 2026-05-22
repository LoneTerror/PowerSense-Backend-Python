import subprocess
import sys
import os
import time
import webbrowser
import argparse

def print_dashboard(auto_docs_enabled: bool):
    os.system('cls' if os.name == 'nt' else 'clear')
    print("="*65)
    print(" 🚀 POWERSENSE DEVELOPMENT CLUSTER ACTIVE")
    print("="*65)

    print("\n 🔐 AUTH SERVICE (Port 8000)")
    print(" ----------------------------------------------------")
    print("   Swagger UI : http://127.0.0.1:8000/v1/auth/docs")
    
    print("\n 🔌 DEVICE SERVICE (Port 8001)")
    print(" ----------------------------------------------------")
    print("   Swagger UI : http://127.0.0.1:8001/v1/relays/docs")

    print("\n 📡 TELEMETRY SERVICE (Port 8002)")
    print(" ----------------------------------------------------")
    print("   Swagger UI : http://127.0.0.1:8002/v1/sensors/docs")

    print("\n 👤 USER SERVICE (Port 8003)")
    print(" ----------------------------------------------------")
    print("   Swagger UI : http://127.0.0.1:8003/v1/users/docs")
    
    print("\n" + "="*65)
    if auto_docs_enabled:
        print(" 🌐 Auto-Docs: ENABLED (Opening tabs...)")
    else:
        print(" 🌐 Auto-Docs: DISABLED (Run with --docs to enable)")
    print("="*65 + "\n")

def open_swagger_docs():
    """Opens all Swagger UI pages in the default web browser."""
    urls = [
        "http://127.0.0.1:8000/v1/auth/docs",
        "http://127.0.0.1:8001/v1/relays/docs",
        "http://127.0.0.1:8002/v1/sensors/docs",
        "http://127.0.0.1:8003/v1/users/docs"
    ]
    for url in urls:
        webbrowser.open_new_tab(url)
        time.sleep(0.2) # Slight delay prevents browser from freezing with rapid requests

def main():
    # 1. Setup the command-line toggle
    parser = argparse.ArgumentParser(description="Start the PowerSense Cluster.")
    parser.add_argument('--docs', action='store_true', help="Automatically open Swagger UI tabs on startup")
    args = parser.parse_args()

    print_dashboard(auto_docs_enabled=args.docs)
    
    uvicorn = os.path.join("venv", "Scripts", "uvicorn") if os.name == "nt" else os.path.join("venv", "bin", "uvicorn")

    auth_cmd = [uvicorn, "src.auth.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"]
    device_cmd = [uvicorn, "src.device.main:app", "--host", "127.0.0.1", "--port", "8001", "--reload"]
    telemetry_cmd = [uvicorn, "src.telemetry.main:app", "--host", "127.0.0.1", "--port", "8002", "--reload"]
    user_cmd = [uvicorn, "src.user.main:app", "--host", "127.0.0.1", "--port", "8003", "--reload"]

    try:
        p0 = subprocess.Popen(auth_cmd)
        time.sleep(0.5)
        p1 = subprocess.Popen(device_cmd)
        time.sleep(0.5) 
        p2 = subprocess.Popen(telemetry_cmd)
        time.sleep(0.5)
        p3 = subprocess.Popen(user_cmd)
        
        # 2. If the toggle is active, give Uvicorn 2 seconds to bind to the ports, then open tabs
        if args.docs:
            time.sleep(2.0)
            open_swagger_docs()
        
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