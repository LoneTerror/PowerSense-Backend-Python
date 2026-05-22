import os
from fastapi import FastAPI
from dotenv import load_dotenv

from src.auth.router import router as auth_router
from src.common.cors_setup import initialize_cors
from src.common.middleware import (
    request_timing_middleware,
    generic_exception_handler
)

load_dotenv()
ENABLE_DOCS = os.getenv("ENABLE_API_DOCS", "True").lower() == "true"
USE_NGINX = os.getenv("USE_NGINX", "False").lower() == "true"

# Define the routing options
nginx_server = {"url": "/", "description": "Current Host (Auto-Detect)"}
local_server = {"url": "http://127.0.0.1:8000", "description": "Direct Localhost"}

# Dynamically sort the servers array based on your .env file
active_servers = [nginx_server, local_server] if USE_NGINX else [local_server, nginx_server]

app = FastAPI(
    title="PowerSense Auth Service",
    version="1.0.0",
    docs_url="/v1/auth/docs" if ENABLE_DOCS else None,
    openapi_url="/v1/auth/openapi.json" if ENABLE_DOCS else None,
    redoc_url=None, # Optional: Disable redoc or route it similarly
    servers=active_servers
)

initialize_cors(app)
app.middleware("http")(request_timing_middleware)
app.add_exception_handler(Exception, generic_exception_handler)

@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "Auth Service Online"}

app.include_router(auth_router)