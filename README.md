# PowerSense Backend

An industrial-grade IoT Power Monitoring and Relay Control backend. 

This repository has been migrated from a legacy Node.js monolith to a **Python FastAPI Microservices Monorepo** architecture, utilizing SQLAlchemy, Alembic, and PostgreSQL.

## 🏗️ Architecture

The backend is split into dedicated, scalable microservices sharing a centralized PostgreSQL database:

* **Telemetry Service (Port 8002):** Handles high-frequency data ingestion and WebSocket broadcasting for the ESP8266 and Android dashboards.
* **Device Service (Port 8001):** Manages relay configurations, state toggling, and logging.
* **Shared DB Library:** A centralized `shared/powersense_db` module containing all SQLAlchemy ORM models and Alembic migration scripts to ensure a Single Source of Truth.

## ⚙️ Prerequisites

1.  **Python 3.10.x** must be installed and added to your system PATH.
2.  **Docker** must be installed to run the PostgreSQL database.

## 🐳 Starting the Database

Before running any backend code, you must start the PostgreSQL container. Based on the `.env` configuration, run the following Docker command:

```bash
docker run --name postgres -e POSTGRES_USER=db-user -e POSTGRES_PASSWORD=db-password -e POSTGRES_DB=db-name -p 5432:5432 -d postgres