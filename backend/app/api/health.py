from fastapi import APIRouter
from fastapi import HTTPException

from app.db.health import check_database_connection

router = APIRouter()


@router.get("/api/health")
def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "application": "FindAI",
        "version": "0.1.0",
    }


@router.get("/api/health/database")
def database_health_check() -> dict[str, str]:
    if not check_database_connection():
        raise HTTPException(
            status_code=503,
            detail="Database connection unavailable",
        )

    return {"status": "healthy", "database": "connected"}
