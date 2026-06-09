from fastapi import APIRouter
router = APIRouter()


@router.get("/{team_code}")
def get_news(team_code: str):
    return []
