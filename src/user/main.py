import os
from fastapi import FastAPI
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from sqlalchemy import select

from src.user.router import router as user_router
from src.user.admin_router import router as admin_router
from src.common.cors_setup import initialize_cors
from src.common.middleware import (
    request_timing_middleware,
    generic_exception_handler
)

# Import DB components for the seed function
from src.database.client import get_db
from src.database.models import RolePolicy

# Force load the .env file
load_dotenv()

ENABLE_DOCS = os.getenv("ENABLE_DOCS", "True").lower() == "true"

# ==========================================
# DATABASE SEEDING LOGIC
# ==========================================
async def seed_default_roles():
    """Automatically injects the consumer RBAC policies."""
    async for db in get_db():
        
        all_system_routes = [
            "/health",
            "/v1/auth/signup",
            "/v1/auth/login",
            "/v1/auth/forgot-password",
            "/v1/auth/reset-password",
            "/v1/auth/users",
            "/v1/relays/config",
            "/v1/relays/{relay_id}/config",
            "/v1/relays/{relay_id}/toggle",
            "/v1/sensors/latest",
            "/v1/users/me",
            "/v1/users/me/change-password",
            "/v1/admin/users",
            "/v1/admin/users/{user_id}",
            "/v1/admin/system-routes",
            "/v1/admin/roles",
            "/v1/admin/roles/{role_name}"
        ]

        # Clean, 3-Tier Consumer Matrix
        default_policies = {
            "viewer": [  # Read-only guest access (Family members, kids, etc.)
                "/v1/sensors/latest",
                "/v1/relays/config",
                "/v1/users/me",
                "/v1/users/me/change-password"
            ],
            "default": [ # Standard consumer access (Can toggle their devices)
                "/v1/sensors/latest",
                "/v1/relays/config",
                "/v1/relays/{relay_id}/toggle",
                "/v1/users/me",
                "/v1/users/me/change-password"
            ],
            "admin": all_system_routes # Full master access
        }

        for role_name, endpoints in default_policies.items():
            query = select(RolePolicy).where(RolePolicy.name == role_name)
            result = await db.execute(query)
            
            if not result.scalar_one_or_none():
                new_policy = RolePolicy(name=role_name, allowed_endpoints=endpoints)
                db.add(new_policy)
                print(f"🌱 SEEDED: Consumer Role '{role_name}' injected into database.")
                
        await db.commit()
        break

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Executes startup and shutdown events."""
    await seed_default_roles()
    yield
    # (Any shutdown logic would go here)

# ==========================================
# APP INITIALIZATION
# ==========================================
# Force Auto-Detect as the primary default for Swagger UI
active_servers = [
    {"url": "/", "description": "Current Host (Auto-Detect)"},
    {"url": "http://127.0.0.1:8003", "description": "Direct Localhost"}
]

# Pass the lifespan context manager into the FastAPI app
app = FastAPI(
    title="PowerSense User Management Service",
    version="1.0.0",
    docs_url="/v1/users/docs" if ENABLE_DOCS else None,
    openapi_url="/v1/users/openapi.json" if ENABLE_DOCS else None,
    servers=active_servers,
    lifespan=lifespan
)

initialize_cors(app)
app.middleware("http")(request_timing_middleware)
app.add_exception_handler(Exception, generic_exception_handler)

@app.get("/v1/users/health", tags=["System"])
async def health_check():
    return {"status": "User Service Online", "port": 8003}

app.include_router(user_router)
app.include_router(admin_router)