# automated_run.py
import subprocess
import sys
import os
import socket
import logging
from datetime import datetime

PYTHON_VERSION_REQUIRED = "3.10"

# --- LOGGING SETUP ---
LOG_DIR = "logger"

# Create the logger folder if it doesn't exist
os.makedirs(LOG_DIR, exist_ok=True)

# Generate a dynamic filename with the current date and time
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
LOG_FILE = os.path.join(LOG_DIR, f"powersense_setup_{timestamp}.log")

# Force UTF-8 encoding for Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def run_command(command, env=None, cwd=None):
    logger.info(f"Executing: {command}")
    result = subprocess.run(command, shell=True, env=env, cwd=cwd, capture_output=True, text=True)
    if result.stdout:
        logger.info(result.stdout.strip())
    if result.stderr:
        logger.error(result.stderr.strip())
        
    if result.returncode != 0:
        logger.error(f"❌ Command failed with exit code {result.returncode}: {command}")
        sys.exit(result.returncode)

def check_python_version():
    if not sys.version.startswith(PYTHON_VERSION_REQUIRED):
        logger.error(f"❌ Python {PYTHON_VERSION_REQUIRED}.x is required. Found: {sys.version}")
        sys.exit(1)
    logger.info(f"✅ Python version validated: {sys.version.split()[0]}")

def check_database():
    logger.info("🔍 Reading database config from .env...")
    host = "localhost"
    port = 5442
    
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("DATABASE_URL="):
                    try:
                        address_part = line.split("@")[1].split("/")[0]
                        host = address_part.split(":")[0]
                        port = int(address_part.split(":")[1])
                    except Exception as e:
                        logger.warning(f"⚠️ Could not parse DATABASE_URL: {e}")
                    break

    logger.info(f"🔍 Pinging remote database on {host}:{port}...")
    try:
        with socket.create_connection((host, port), timeout=5):
            logger.info(f"✅ Database is reachable on {host}:{port}.")
    except OSError:
        logger.error(f"❌ Database connection failed on {host}:{port}.")
        logger.error("⚠️ Ensure your remote PostgreSQL instance is running.")
        sys.exit(1)

def git_pull():
    logger.info("🔄 Pulling latest changes from Git...")
    run_command("git pull")

def venv_create():
    logger.info("🛠️ Creating Virtual Environment...")
    python_cmd = "py -3.10" if os.name == "nt" else "python3.10"
    if not os.path.exists("venv"):
        run_command(f"{python_cmd} -m venv venv")
        logger.info("✅ Virtual Environment created.")
    else:
        logger.info("⚡ Virtual Environment already exists. Skipping creation.")

def dependencies_installation():
    logger.info("📦 Installing requirements...")
    python_path = os.path.join("venv", "Scripts", "python") if os.name == "nt" else os.path.join("venv", "bin", "python")
    run_command(f"{python_path} -m pip install --upgrade pip")
    if os.path.exists("requirements.txt"):
        run_command(f"{python_path} -m pip install -r requirements.txt")
        logger.info("✅ Dependencies installed successfully.")
    else:
        logger.warning("⚠️ No requirements.txt found. Skipping dependency installation.")

def alembic_upgrade():
    logger.info("⚙️ Running Alembic Database Migrations...")
    check_database()
    alembic_path = os.path.join("venv", "Scripts", "alembic") if os.name == "nt" else os.path.join("venv", "bin", "alembic")
    shared_db_path = os.path.join("shared", "powersense_db")
    
    if os.path.exists(shared_db_path):
        run_command(f"{alembic_path} upgrade head", cwd=shared_db_path)
        logger.info("✅ Database schema is up to date.")
    else:
        logger.error(f"❌ Could not find {shared_db_path}.")

def run_all_setup():
    logger.info("🚀 Running FULL automated setup...")
    git_pull()
    venv_create()
    dependencies_installation()
    alembic_upgrade()
    logger.info("✅ Full setup complete! Use fast-run.py or run.py to start servers.")

def exit_and_activate():
    logger.info("🛑 Exiting script. Handing control to PowerShell to activate venv...")
    sys.exit(42)

def exit_program():
    logger.info("🛑 Exiting automation script without activating venv.")
    sys.exit(0)

switch = {
    "1": git_pull,
    "2": venv_create,
    "3": dependencies_installation,
    "4": check_database,
    "5": alembic_upgrade,
    "6": run_all_setup,
    "7": exit_and_activate,
    "8": exit_program
}

if __name__ == "__main__":
    logger.info("=== PowerSense Automation Script Started ===")
    check_python_version()

    while True:
        print("\n========== PowerSense Setup Automation ==========")
        print("1. Git Pull")
        print("2. Create Virtual Environment (Python 3.10)")
        print("3. Install/Update Dependencies")
        print("4. Check PostgreSQL Database Status")
        print("5. Run Database Migrations (Alembic)")
        print("6. Run Full Setup { recommended }")
        print("7. Exit + Activate Venv { recommended }")
        print("8. Exit")
    
        choice = input("\nChoose option (1-8): ").strip()
        action = switch.get(choice)
    
        if action:
            action()
        else:
            logger.warning("❌ Invalid option selected.")