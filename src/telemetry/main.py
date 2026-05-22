import os
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse
from fastapi.openapi.utils import get_openapi
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import IntegrityError
from dotenv import load_dotenv

from src.telemetry.router import router as telemetry_router
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

# Force Auto-Detect as the primary default for Swagger UI
active_servers = [
    {"url": "/", "description": "Current Host (Auto-Detect)"},
    {"url": "http://127.0.0.1:8002", "description": "Direct Localhost"}
]

app = FastAPI(
    title="PowerSense Telemetry Service",
    version="1.0.0",
    docs_url="/v1/sensors/docs" if ENABLE_DOCS else None,
    openapi_url="/v1/sensors/openapi.json" if ENABLE_DOCS else None,
    redoc_url="/v1/sensors/redoc" if ENABLE_DOCS else None,
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
    return {"status": "healthy", "service": "Telemetry Service"}

@app.get("/", include_in_schema=False)
async def root_redirect():
    """Automatically redirects base URL visitors to the Swagger UI."""
    return RedirectResponse(url="/v1/sensors/docs")

app.include_router(telemetry_router)