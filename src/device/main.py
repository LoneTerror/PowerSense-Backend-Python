import os
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse
from fastapi.openapi.utils import get_openapi
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import IntegrityError
from dotenv import load_dotenv

from src.device.router import router as device_router
from src.common.cors_setup import initialize_cors
from src.common.middleware import (
    request_timing_middleware,
    sqlalchemy_integrity_handler,
    validation_exception_handler,
    http_exception_handler,
    generic_exception_handler
)

load_dotenv()
ENABLE_DOCS = os.getenv("ENABLE_API_DOCS", "True").lower() == "true"
USE_NGINX = os.getenv("USE_NGINX", "False").lower() == "true"

# Define the routing options
nginx_server = {"url": "/powersense/v1/relays", "description": "API Gateway Route (Nginx)"}
local_server = {"url": "http://127.0.0.1:8001", "description": "Direct Localhost"}

# Dynamically sort the servers array
active_servers = [nginx_server, local_server] if USE_NGINX else [local_server, nginx_server]

app = FastAPI(
    title="PowerSense Device Service",
    version="1.0.0",
    docs_url="/docs" if ENABLE_DOCS else None,
    redoc_url="/redoc" if ENABLE_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_DOCS else None,
    servers=active_servers
)

initialize_cors(app)
app.middleware("http")(request_timing_middleware)

app.add_exception_handler(IntegrityError, sqlalchemy_integrity_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "healthy", "service": "Device Service"}

@app.get("/", include_in_schema=False)
async def root_redirect():
    """Automatically redirects base URL visitors to the Swagger UI."""
    return RedirectResponse(url="/docs")

app.include_router(device_router)