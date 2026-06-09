from fastapi import APIRouter
router = APIRouter()


@router.get("/value")
def get_value():
    return []


@router.get("/acca")
def get_acca(k: int = 4):
    return []


@router.post("/sgm")
def build_sgm(match_id: str, markets: list[str]):
    return {}
