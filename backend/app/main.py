import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router

load_dotenv()

app = FastAPI(title="FindAI API", version="0.1.0")

frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
allowed_origins = list(
    dict.fromkeys([frontend_url, "http://127.0.0.1:5173"])
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)


@app.get("/")
def read_root() -> dict[str, str]:
    return {
        "message": "Welcome to FindAI API",
        "application": "FindAI",
        "docs": "/docs",
    }
