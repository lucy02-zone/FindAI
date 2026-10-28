from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.items import router as items_router
from app.api.users import router as users_router
from app.core.config import settings

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)

frontend_url = settings.FRONTEND_URL.rstrip("/")
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
app.include_router(auth_router, prefix="/api/auth")
app.include_router(items_router, prefix="/api/items")
app.include_router(users_router, prefix="/api/users")


@app.get("/")
def read_root() -> dict[str, str]:
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "application": settings.APP_NAME,
        "docs": "/docs",
    }
