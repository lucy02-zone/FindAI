from fastapi import APIRouter

router = APIRouter()


@router.get("/api/health")
def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "application": "FindAI",
        "version": "0.1.0",
    }
