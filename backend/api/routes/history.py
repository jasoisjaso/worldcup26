from fastapi import APIRouter
router = APIRouter()


@router.get("")
def get_history():
    return []


@router.get("/stats")
def get_stats():
    return {"accuracy": 0, "avg_ev": 0, "roi": 0, "total": 0, "correct": 0}
