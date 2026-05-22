# PowerSense Core API ⚡

An industrial-grade, consumer-facing Smart Home IoT backend built with a 4-port FastAPI microservice architecture. 

PowerSense utilizes a Zero-Trust Role-Based Access Control (RBAC) system, fully isolated data telemetry, and an automated continuous deployment pipeline tailored for containerized environments (Pterodactyl/Docker) behind an Nginx reverse proxy.

---

## 🏗️ System Architecture

The backend is decoupled into four highly specialized microservices communicating via a centralized PostgreSQL database.

| Service | Port | Description |
| :--- | :--- | :--- |
| **Auth Service** | `8000` | Manages JWT generation, user registration, and authentication flows. |
| **Device Service** | `8001` | Handles IoT relay configurations and state toggling for smart home hardware. |
| **Telemetry Service** | `8002` | High-frequency ingestion and retrieval of live sensor data (voltage, wattage). |
| **User Service** | `8003` | Admin RBAC management, system route scraping, and profile modifications. |

### Security & RBAC
The system strictly enforces a 3-tier consumer security matrix:
* `viewer`: Read-only access to sensor data and personal profile.
* `default`: Standard smart-home user. Can toggle relays and view telemetry.
* `admin`: Master access to all 23 system routes, user provisioning, and role modification.

---

## 🛠️ Tech Stack

* **Framework:** [FastAPI](https://fastapi.tiangolo.com/) (Python 3.10+)
* **Server:** Uvicorn (ASGI)
* **Database:** PostgreSQL
* **ORM & Migrations:** SQLAlchemy (Async) + Alembic
* **Deployment:** Nginx Proxy + Pterodactyl (Docker)

---