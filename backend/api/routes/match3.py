from fastapi import APIRouter
router = APIRouter()


@router.get("")
def get_match3_alerts():
    return []
