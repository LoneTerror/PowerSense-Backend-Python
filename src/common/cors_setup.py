from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

def initialize_cors(app: FastAPI):
    """Configures Cross-Origin Resource Sharing."""
    
    # In production, this should be restricted to your specific frontend domains
    ALLOWED_ORIGINS = [
        "http://localhost:3000",      # React/Next.js frontend (if applicable)
        "http://127.0.0.1:3000",
        "https://powersense.top",     # Production frontend
        "*"                           # Open for mobile app testing, tighten later
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )