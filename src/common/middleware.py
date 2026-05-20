from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import IntegrityError
import time
import logging

logger = logging.getLogger(__name__)

async def request_timing_middleware(request: Request, call_next):
    """Calculates the processing time of each request for observability."""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    # Adds a custom header that Nginx or Jaeger can read later
    response.headers["X-Process-Time"] = str(process_time)
    return response

async def sqlalchemy_integrity_handler(request: Request, exc: IntegrityError):
    """Catches database constraint violations (e.g., duplicate IDs)."""
    logger.error(f"Database Integrity Error on {request.url.path}: {exc.orig}")
    return JSONResponse(
        status_code=409,
        content={"error": "Conflict", "detail": "A database constraint was violated."}
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Formats Pydantic validation errors into a clean, readable list."""
    errors = [{"field": e["loc"][-1], "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(
        status_code=422,
        content={"error": "Validation Error", "details": errors}
    )

async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Standardizes all manual HTTPExceptions thrown in the routers."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "HTTP Error", "detail": exc.detail}
    )

async def generic_exception_handler(request: Request, exc: Exception):
    """The ultimate fallback to prevent the server from leaking stack traces to the client."""
    logger.error(f"Unhandled Exception on {request.url.path}: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error", "detail": "An unexpected error occurred."}
    )